# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 09:00:48 2020
@author: Micha

To do:
    CA Charts
        -Add mouseover to CA ICU and hospitalization charts
    County Charts
        -Add county hospitalization/ICU charts
        -Add mouseover to ICU charts
    Make chloropleths
"""
#%% Config
import pandas as pd
from bokeh.plotting import figure, show, save
from bokeh.models import NumeralTickFormatter,ColumnDataSource,HoverTool, Range1d,Panel,Tabs,Div,LinearAxis
from bokeh.layouts import layout,row,Spacer
from bokeh.palettes import Category20
import itertools
from datetime import timedelta
import math
from bs4 import BeautifulSoup as Soup
import requests
import json

import config

fileloc=config.fileloc
mode=config.mode
base_url=config.base_url

state='CA'
counties=['Sacramento','El Dorado','Placer','Yolo']
#%% Data Imports
#Tests and National Stats
print("Getting national statistics...")
url='https://covidtracking.com/api/v1/states/daily.json'
df=pd.read_json(url)
df['Date']=pd.to_datetime(df.date, format='%Y%m%d', errors='ignore')
df=df[df['Date']>='2020-03-15']

url="https://gist.githubusercontent.com/mshafrir/2646763/raw/8b0dbb93521f5d6889502305335104218454c2bf/states_hash.json"
state_mapping=json.loads(requests.get(url).content)
df['STATE']=df.state.map(state_mapping).str.upper()

def rolling_7_avg(df,date,group,field):
    newname=field+'_avg'
    df.sort_values(by=[group,date],inplace=True)
    df2=df.sort_values(by=[group,date]).assign(newname=df.groupby([group], as_index=False)[[field]].rolling(7,min_periods=7).mean().reset_index(0, drop=True))
    return df2.rename(columns={"newname": newname})

fields=['totalTestResultsIncrease','deathIncrease','positiveIncrease']

for field in fields:
    df=rolling_7_avg(df,'Date','state',field)

df['positivity']=df.positiveIncrease_avg/df.totalTestResultsIncrease_avg

#CA Data
url='https://data.ca.gov/dataset/590188d5-8545-4c93-a9a0-e230f0db7290/resource/926fd08f-cc91-4828-af38-bd45de97f8c3/download/statewide_cases.csv'
caCases=pd.read_csv(url,delimiter=',')
url='https://data.ca.gov/dataset/529ac907-6ba1-4cb7-9aae-8966fc96aeef/resource/42d33765-20fd-44b8-a978-b083b7542225/download/hospitals_by_county.csv'
caHosp=pd.read_csv(url,delimiter=',')
caHosp = caHosp[pd.notnull(caHosp['todays_date'])]
caHosp = caHosp[pd.notnull(caHosp['county'])]
caData=caCases.merge(caHosp, how='left', left_on=['county','date'], right_on=['county','todays_date'])
caData['Date']=pd.to_datetime(caData['date'], format='%Y-%m-%d')
caData['COUNTY']=caData['county'].str.upper()
caData.rename(columns={'county':'County'}, inplace=True)
caData.drop(columns=['date','todays_date'], inplace=True)

#hospital capacity
print("Getting hospital capacity...")
url='https://data.chhs.ca.gov/datastore/dump/0997fa8e-ef7c-43f2-8b9a-94672935fa60?q=&sort=_id+asc&fields=FACID%2CFACNAME%2CFAC_FDR%2CBED_CAPACITY_TYPE%2CBED_CAPACITY%2CCOUNTY_NAME&filters=%7B%7D&format=csv'
df3=pd.read_csv(url,delimiter=',')
hospital_capacity=df3[df3['FAC_FDR']=='GENERAL ACUTE CARE HOSPITAL'].groupby('COUNTY_NAME').sum()['BED_CAPACITY']
ICU_capacity=df3[(df3['FAC_FDR']=='GENERAL ACUTE CARE HOSPITAL')&(df3['BED_CAPACITY_TYPE']=='INTENSIVE CARE')].groupby('COUNTY_NAME').sum()['BED_CAPACITY']
hospital_capacity.rename("hospital_capacity",inplace=True)
ICU_capacity.rename("ICU_capacity",inplace=True)
caData=caData.merge(hospital_capacity,left_on='COUNTY', right_index=True, how='left').merge(ICU_capacity,left_on='COUNTY', right_index=True, how='left')

#County Population
print("Getting county populations...")
url='https://www2.census.gov/programs-surveys/popest/datasets/2010-2019/counties/totals/co-est2019-alldata.csv'
df4=pd.read_csv(url,delimiter=',',encoding='latin-1')
statepop=df4.groupby('STNAME').sum().POPESTIMATE2019.to_frame(name="pop")
statepop['STATE']=statepop.index.str.upper()
df=df.merge(statepop,how='left',on='STATE')
df4=df4[(df4['STATE']==6)&(df4['COUNTY']>0)]
df4['county']=df4['CTYNAME'].str.replace(' County','').str.upper()
df4=df4[['county','POPESTIMATE2019']]
caData=caData.merge(df4, left_on='COUNTY',right_on='county')
caData.rename(columns={"POPESTIMATE2019": "pop"},inplace=True)

"""#Accelerated Reopening
print("Getting accelerated reopening plans...")
url='https://www.cdph.ca.gov/Programs/CID/DCDC/Pages/COVID-19/County_Variance_Attestation_Form.aspx'
soup = bs(r.get(url).content, 'html.parser')
list=soup.findAll("div", {"class": "NewsItemContent"})[0].findAll("ul")[1].findAll("li")
accel_counties=[]
for item in list:
    for i in (item.findAll("a")[0].text.replace("County","").strip().split('-')):
        accel_counties.append(i)
"""

#County Data calculated fields
caData['hospitalized_confirmed_nonICU']=(caData['hospitalized_covid_confirmed_patients']-caData['icu_covid_confirmed_patients']).clip(0)
caData['hospitalized_suspected_nonICU']=(caData['hospitalized_suspected_covid_patients']-caData['icu_suspected_covid_patients']).clip(0)
caData['hospitalized']=caData['hospitalized_covid_patients']
caData['ICU']=caData['icu_covid_confirmed_patients']+caData['icu_suspected_covid_patients']
caData['ICU_usage']=caData['ICU']/caData['ICU_capacity']*100
caData['hospital_usage']=caData['hospitalized']/caData['hospital_capacity']*100
caData.sort_values(by=['county','Date'],inplace=True)
mask=~(caData.county.shift(1)==caData.county)
caData['positiveIncrease']=caData['newcountconfirmed'].clip(0)
caData['deathIncrease']=caData['newcountdeaths'].clip(0)
caData['noncovid_icu']=caData.ICU_capacity-caData.ICU-caData.icu_available_beds

fields=['positiveIncrease','deathIncrease']

for field in fields:
    caData=rolling_7_avg(caData,'Date','COUNTY',field)
    
fields=['positiveIncrease','deathIncrease','positiveIncrease_avg','deathIncrease_avg','hospitalized','ICU']
for field in fields:
    caData[field+'_percap']=caData[field]/caData['pop']*100000

fields=['totalTestResultsIncrease_avg','deathIncrease_avg','positiveIncrease_avg','hospitalizedCurrently']
for field in fields:
    df[field+'_percap']=df[field]/df['pop']*100000

regions=['US',state]
charts=['Tests','Cases','Deaths']

#%% National

#All states in one chart
def statecompare(metric,metricname,foci):
    palette=Category20[20]
    colors = itertools.cycle(palette)
    p = figure(title=metricname, x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
                y_range=Range1d(0,math.ceil(df[metric].max()), bounds=(0,math.ceil(df[metric].max()*1.5/10)*10)),
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
    grp_list = df.groupby('state').max().positive.nlargest(15).index.sort_values()
    lines={}
    for i,color in zip(range(len(grp_list)),colors):
        source = ColumnDataSource(
        data={'Date':df.loc[df.state == grp_list[i]].Date,
               'state':df.loc[df.state == grp_list[i]].state,
               metric:df.loc[df.state == grp_list[i]][metric]})
        lines[grp_list[i]]=p.line(x='Date',
                y=metric,
                source=source,
                legend_label = grp_list[i],
                color=color,
                alpha=1,
                width=2,
                muted_width=1,
                muted_color = 'grey',
                muted_alpha=0.4,
                muted = True)
    for focus in foci:
        lines[focus].muted=False
    hover = HoverTool(tooltips =[
         ('State','@state'),('Date','@Date{%F}'),(metricname,'@'+metric+'{0,}')],
         formatters={'@Date': 'datetime'})
    p.add_tools(hover)
    p.yaxis.formatter=NumeralTickFormatter(format="0,")
    p.legend.location = "top_left"
    p.legend.click_policy="mute"
    p.legend.label_text_font_size="8pt"

    return p

def percap(metric,metricname,foci):
    gross=Panel(child=statecompare(metric,metricname,foci),title='Gross')
    percap_chart=statecompare(metric+'_percap',metricname+' per 100k population',foci)
    percap_chart.hover._property_values['tooltips'][2]=(metricname+' per 100k', '@'+metric+'_percap{0.0}')
    percap_chart.yaxis.formatter=NumeralTickFormatter(format="0.0")
    percap=Panel(child=percap_chart,title='Per 100k')
    return Tabs(tabs=[gross,percap])

padding=Spacer(width=30, height=10, sizing_mode='fixed')

foci=['CA','AZ','FL','GA','TX','NC','LA']

state_cases=percap('positiveIncrease_avg','New Cases (7-day avg)',foci)
state_hospitalizations=percap('hospitalizedCurrently','Hospitalized',foci)
state_deaths=percap('deathIncrease_avg','Deaths (7-day avg)',foci)
positivity=statecompare('positivity','Positivity (7-day avg)',foci)

positivity.y_range=Range1d(0,0.6,bounds=(0,math.ceil(df['positivity'].max()*1.05/10)*10))
positivity.yaxis.formatter=NumeralTickFormatter(format="0%")
positivity.hover._property_values['tooltips'][2]=('Positivity (7-day avg)', '@positivity{0.0%}')

state_deaths.tabs[0].child.y_range=Range1d(0,math.ceil(df[~df.state.isin(['NY','NJ'])].deathIncrease_avg.max()*1.05), bounds=(0,math.ceil(df.deathIncrease_avg.max()*1.5)))

nation_sum=df.groupby('Date').sum()
nation_sum['positivity_avg']=nation_sum.positiveIncrease_avg/nation_sum.totalTestResultsIncrease_avg
nation_sum['positivity']=nation_sum.positiveIncrease/nation_sum.totalTestResultsIncrease

fields=['totalTestResultsIncrease','positiveIncrease']


source=ColumnDataSource(nation_sum)
nation=figure(title='National', x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
nation.extra_y_ranges = {"deaths": Range1d(start=0, end=df.groupby('Date').sum().deathIncrease.max())}
nation.add_layout(LinearAxis(y_range_name="deaths", axis_label='Deaths'), 'right')
nation.yaxis.formatter=NumeralTickFormatter(format="0,")

nation.line(x='Date', y='deathIncrease_avg', source=source,legend_label = 'Avg Deaths', color='red',y_range_name="deaths",width=2)
nation.line(x='Date', y='deathIncrease', source=source,legend_label = 'Daily Deaths', color='red',y_range_name="deaths",alpha=0.2)
nation.line(x='Date', y='hospitalizedCurrently', source=source,legend_label = 'Hospitalized', color='orange',width=2)
nation.line(x='Date', y='positiveIncrease_avg', source=source,legend_label = 'Avg Cases', color='green',width=2)
nation.line(x='Date', y='positiveIncrease', source=source,legend_label = 'Daily Cases', color='green',alpha=0.2)
nation.yaxis[0].axis_label = 'Cases, Hospitalization'
nation.legend.location = "top_left"
hover = HoverTool(tooltips =[
     ('Date','@Date{%F}'),
     ('Cases','@positiveIncrease{0,}'),
     ('Avg Cases','@positiveIncrease_avg{0,}'),
     ('Hospitalized','@hospitalizedCurrently{0,}'),
     ('Deaths','@deathIncrease{0,}'),
     ('Avg Deaths','@deathIncrease_avg{0,}'),
     ],
     formatters={'@Date': 'datetime'})
nation.add_tools(hover)

nation_positivity=figure(title='Positivity', x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
nation_positivity.line(x='Date', y='positivity_avg', source=source,legend_label = 'Avg Positivity', color='blue',width=2)
nation_positivity.line(x='Date', y='positivity', source=source,legend_label = 'Positivity', color='blue',alpha=0.2)
hover = HoverTool(tooltips =[
     ('Date','@Date{%F}'),
     ('Positivity','@positivity{0.0%}'),
     ('Avg Positivity','@positivity_avg{0.0%}'),
     ],
     formatters={'@Date': 'datetime'})
nation_positivity.add_tools(hover)
nation_positivity.yaxis.formatter=NumeralTickFormatter(format="0%")


nationalcharts=Panel(child=
                         layout([[nation,nation_positivity,padding],[state_cases,positivity,padding],[state_hospitalizations,state_deaths,padding]],
                         sizing_mode='stretch_width',
                         ),
                     title='National')

#%% State 

source = ColumnDataSource(df[df.state=='CA'])

def statechart(metric,metricname):
    p=figure(x_axis_type='datetime',
               plot_height=400,
               sizing_mode='stretch_width',
               title=metricname,
               toolbar_location='above',
               tools=[HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Average '+metricname,'@'+metric+'_avg{0,}'),
                   ('Daily '+metricname,'@'+metric+'{0,}'),
                   ],
                   formatters={'@Date': 'datetime'})]
            )
    p.line(x='Date', y=metric, source=source, color='grey',legend_label='Daily')
    p.line(x='Date', y=metric+'_avg', source=source, color='blue',width=2, legend_label='7-day average')
    p.yaxis.formatter=NumeralTickFormatter(format="0,")
    p.legend.location = "top_left"
    padding=Spacer(width=30, height=10, sizing_mode='fixed')
    return(row([p,padding]))

tests=statechart('totalTestResultsIncrease','Tests')
cases=statechart('positiveIncrease','Cases')
deaths=statechart('deathIncrease','Deaths')

#Hospitalizations
ca=caData.groupby(['Date']).sum().sort_values(by=['Date'])
ca=ca[ca.index>='2020-04-01']
hospitalizations=figure(x_axis_type='datetime',
               plot_height=400,
               sizing_mode='stretch_width',
               title='Hospitalizations',
               toolbar_location='above',
               tools=[HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Hospitalized Confirmed','@hospitalized_confirmed_nonICU{0,}'),
                   ('Hospitalized Suspected','@hospitalized_suspected_nonICU{0,}'),
                   ('ICU Confirmed','@icu_covid_confirmed_patients{0,}'),
                   ('ICU Suspected','@icu_suspected_covid_patients{0,}'),
                   ],
                   formatters={'@Date': 'datetime'})]
            )
hospitalizations.varea_stack(['hospitalized_confirmed_nonICU','hospitalized_suspected_nonICU','icu_covid_confirmed_patients','icu_suspected_covid_patients'], x='Date', color=['green','yellow','orange','red'],
                             legend_label=['Hospitalized Confirmed','Hospitalized Suspected','ICU Confirmed','ICU Suspected'],
                             source=ColumnDataSource(ca))

hospitalizations.vline_stack(['hospitalized_confirmed_nonICU','hospitalized_suspected_nonICU','icu_covid_confirmed_patients','icu_suspected_covid_patients'], x='Date', source=ColumnDataSource(ca),alpha=0)

hospitalizations.yaxis.formatter=NumeralTickFormatter(format="0,")
hospitalizations.legend.location = "top_left"

#ICU
casource = ColumnDataSource(caData.groupby('Date').sum())
icu = figure(x_axis_type='datetime',
           plot_height=400,
           sizing_mode='stretch_width',
           title="ICU Capacity",
           toolbar_location='above',
           tools=[HoverTool(tooltips=[
               ('Date','@Date{%F}'),
               ('ICU','@ICU{0,}'),
               ('Non-COVID ICU','@noncovid_icu{0,}'),
               ('Available Beds','@icu_available_beds{0,}'),
               ],
               formatters={'@Date': 'datetime'})]
        )
icu.varea_stack(['ICU','noncovid_icu','icu_available_beds'], x='Date', color=['red','yellow','green'], source=casource,
              legend_label=['COVID Cases','Non-COVID Cases','Available Beds'])
icu.vline_stack(['ICU','noncovid_icu','icu_available_beds'], x='Date', source=casource,alpha=0)

icu.yaxis.formatter=NumeralTickFormatter(format="0,")
icu.legend.location = "top_left"


statecharts=Panel(child=
                         layout([[tests,cases,deaths],[hospitalizations,icu,Spacer(width=30, height=10, sizing_mode='fixed')]],
                         sizing_mode='stretch_width',
                         ),
                      title='California')

#%% Counties

def countychart(county):
    source=ColumnDataSource(caData[caData.County==county].groupby('Date').sum())
    cases = figure(x_axis_type='datetime',
                   x_range=Range1d(caData.Date.min(),caData.Date.max(),bounds=(caData.Date.min()-timedelta(days=5),caData.Date.max()+timedelta(days=5))),
                   y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*10))),
                   title=county,
                   plot_height=300,
                   plot_width=100,
                   sizing_mode='stretch_width',
                   toolbar_location='above',
                   tools=["pan,reset,save,wheel_zoom",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Daily New Cases','@positiveIncrease{0,}'),
                   ('7-day average New Cases','@positiveIncrease_avg{0,}')
                   ],
                   formatters={'@Date': 'datetime'})],
                   active_scroll='wheel_zoom')       
    cases.line(x='Date', y='positiveIncrease_percap', source=source, color='grey',legend_label='Daily')
    cases.line(x='Date', y='positiveIncrease_avg_percap', source=source, color='blue',width=2, legend_label='7-day average')
    cases.legend.location = "top_left"
    cases.yaxis.axis_label = 'Cases/100k'
    
    deaths = figure(x_axis_type='datetime',
                    y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*10))),
                   plot_height=300,
                   plot_width=cases.width,
                   toolbar_location='above',
                   tools=["pan,reset,save,xwheel_zoom",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Daily New Deaths','@deathIncrease{0,}'),
                   ('7-day average New Deaths','@deathIncrease_avg{0,}')
                   ],
                   formatters={'@Date': 'datetime'})],
                   active_scroll='xwheel_zoom',
                   sizing_mode = 'scale_width')        
    deaths.line(x='Date', y='deathIncrease', source=source, color='grey',legend_label='Daily')
    deaths.line(x='Date', y='deathIncrease_avg', source=source, color='blue',width=2, legend_label='7-day average')
    deaths.legend.location = "top_left"
    deaths.yaxis.axis_label = 'Deaths'
    
    ICU = figure(x_axis_type='datetime',
                 y_range=Range1d(0,caData[caData.County==county].ICU_capacity.max(), bounds=(0,caData[caData.County==county].ICU_capacity.max())),
               plot_height=300,
               plot_width=cases.width,
               toolbar_location='above',
               tools=["save",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('ICU','@ICU{0,}')
                   ],
                   formatters={'@Date': 'datetime'})],
                   sizing_mode = 'scale_width',
            )
    ICU.varea_stack(['ICU','noncovid_icu','icu_available_beds'], x='Date', color=['red','yellow','green'], source=source,
                  legend_label=['COVID Cases','Non-COVID Cases','Available Beds'])
    ICU.yaxis.formatter=NumeralTickFormatter(format="0,")
    ICU.legend.location = "top_left"
    ICU.yaxis.axis_label = 'ICU Utilization'
    
    deaths.x_range=cases.x_range
    ICU.x_range=cases.x_range
    return layout([[cases],[deaths],[ICU]],sizing_mode='stretch_width')

countycharts=Panel(child=
                       layout(
                       [[countychart('Sacramento'),countychart('El Dorado'),countychart('Placer'),countychart('Yolo'),Spacer(width=30, height=10, sizing_mode='fixed')]],
                       sizing_mode='stretch_width'
                       ),
                   title='Region'
                )

#%% HTML Generation
about_html="""
<p><b>Data Sources and Documentation</b></p>
<p>Source data and documentation available at <a href="https://github.com/skimike02/COVID19Interactive">https://github.com/skimike02/COVID19Interactive</a></p>
<p>National and state data pulled from the <a href="https://covidtracking.com/">COVID Tracking Project</a>, a product of the Atlantic.</p>
<p>CA State and County level data pulled from the <a href="https://data.ca.gov/group/covid-19">CA Open Data Portal</a></p>
<br>
<b>Additional Resources:</b><br>
Official Sites:<br>
<a href="https://www.saccounty.net/COVID-19/Pages/default.aspx">Sacramento County page, including current Public Health Order</a><br>
<a href="https://covid19.ca.gov">CA Main Page</a><br>
<a href="https://www.cdc.gov/coronavirus/2019-ncov/index.html">CDC Main Page</a><br>
<a href="https://www.cdc.gov/nchs/nvss/vsrr/covid19/excess_deaths.htm">CDC Estimate of Excess Deaths</a><br>
<br>Models:<br>
<a href="https://calcat.covid19.ca.gov/cacovidmodels/">Official CA Model</a><br>
<a href="https://www.covid-projections.com/">Historical comparison of models</a><br>
<a href="https://covid19-projections.com/us-ca">A forecast model</a><br>
<a href="https://epiforecasts.io/covid/posts/national/united-states/">Epiforecasts model</a><br>
<a href="https://rt.live/">Estimator of R</a><br>
<br>Vaccines:<br>
<a href="https://vac-lshtm.shinyapps.io/ncov_vaccine_landscape/">Vaccine Tracker w/ Gantt View</a><br>
<a href="https://www.nytimes.com/interactive/2020/science/coronavirus-vaccine-tracker.html">NYT Vaccine Tracker</a><br>
<a href="https://www.raps.org/news-and-articles/news-articles/2020/3/covid-19-vaccine-tracker">RAPS Vaccine Tracker</a><br>
<br>Economic Impacts:<br>
<a href="https://tracktherecovery.org/">Opportunity Insights Tracker</a><br>
<a href="https://help.cuebiq.com/hc/en-us/articles/360041285051-Reading-Cuebiq-s-COVID-19-Mobility-Insights">Cuebiq Mobility Tracker</a><br>
<a href="https://www.jpmorgan.com/global/research">Credit Card Spending</a><br>
<a href="https://www.opentable.com/state-of-industry">OpenTables Reservations</a><br>
<a href="https://www.tsa.gov/coronavirus/passenger-throughput">Flight Volumes</a><br>
"""
about=Panel(child=Div(text=about_html),title='About')


page=Tabs(tabs=[nationalcharts,
                statecharts,
                countycharts,
                about
                ])

mode='prod'
if mode=='dev':
    show(page)
if mode=='prod':
    save(page,resources=None,filename=fileloc+'COVID19.html',title='COVID19')

header=Soup("""
<div class="header">
  <h1 style: {width: 100%}>A selection of tools</h1> 
  <ul class="navigation"> 
    <li><a href="/index.html">Home</a></li> 
    <li><a href="/CAISOData.html">CAISO Data</a></li> 
    <li><a href="/CCAMap">CCA Service Territory</a></li>
    <li><a href="COVID19.html">COVID-19 Data</a></li>
    <li><a href="https://teslaconnect.michaelchamp.com">TeslaConnect</a></li>
  </ul> 
  <link rel="icon" 
      type="image/png" 
      href="https://michaelchamp.com/assets/logo.png">
 <link rel="stylesheet" href="styles.css">
 </div>
""",features='lxml')

footer=Soup("""<div class="footer"> 
  <p>&copy; 2020
    <script>new Date().getFullYear()>2010&&document.write("-"+new Date().getFullYear());</script>
    , Michael Champ</p>
</div>""",features='lxml')

tracker=Soup("""<div><!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=UA-134772498-1"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'UA-134772498-1');
</script></div>""",features='lxml')
    
#Insert script to add custom html header and footer
htmlfile = open(fileloc+'COVID19.html', "r").read()
soup=Soup(htmlfile,"lxml")

soup.find('title').insert_after(header.body.div)
soup.find('body').insert_after(footer.body.div)
soup.find('title').insert_before(tracker.body.div)

f = open(fileloc+'COVID19.html', "w")
f.write(str(soup).replace('©','&copy;'))
