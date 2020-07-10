# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 09:00:48 2020

@author: Micha
"""

import pandas as pd
from bs4 import BeautifulSoup as bs
import requests as r
from bokeh.plotting import figure, output_file, show, save
from bokeh.models import NumeralTickFormatter,ColumnDataSource,CDSView,GroupFilter,HoverTool, Range1d
from bokeh.layouts import layout,gridplot,row
from bokeh.palettes import Category20
from bokeh.transform import factor_cmap
import itertools
from datetime import timedelta
import math


output_file("COVID.html")

state='CA'
counties=['Sacramento','El Dorado','Placer','Yolo']
fileloc=r'C:\\Users\Micha\Documents\GitHub\COVID19Interactive'

#Tests and National Stats
print("Getting national statistics...")
url='https://covidtracking.com/api/v1/states/daily.json'
df=pd.read_json(url)
df['Date']=pd.to_datetime(df.date, format='%Y%m%d', errors='ignore')
df=df[df['Date']>='2020-03-15']

def rolling_7_avg(df,date,group,field):
    newname=field+'_avg'
    df.sort_values(by=[group,date],inplace=True)
    df2=df.sort_values(by=[group,date]).assign(newname=df.groupby([group], as_index=False)[[field]].rolling(7,min_periods=7).mean().reset_index(0, drop=True))
    return df2.rename(columns={"newname": newname})

fields=['totalTestResultsIncrease','deathIncrease','positiveIncrease']

for field in fields:
    df=rolling_7_avg(df,'Date','state',field)

#CA and County Stats
#print("Getting California county statistics...")
#url='https://data.chhs.ca.gov/dataset/6882c390-b2d7-4b9a-aefa-2068cee63e47/resource/6cd8d424-dfaa-4bdd-9410-a3d656e1176e/download/covid19data.csv'
#dfca=pd.read_csv(url,delimiter=',')
#dfca['Date']=pd.to_datetime(dfca['Most Recent Date'], format='%m/%d/%Y')
#dfca['county']=dfca['County Name'].str.upper()

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
df4=df4[(df4['STATE']==6)&(df4['COUNTY']>0)]
df4['county']=df4['CTYNAME'].str.replace(' County','').str.upper()
df4=df4[['county','POPESTIMATE2019']]
caData=caData.merge(df4, left_on='COUNTY',right_on='county')
caData.rename(columns={"POPESTIMATE2019": "pop"},inplace=True)

#Accelerated Reopening
print("Getting accelerated reopening plans...")
url='https://www.cdph.ca.gov/Programs/CID/DCDC/Pages/COVID-19/County_Variance_Attestation_Form.aspx'
soup = bs(r.get(url).content, 'html.parser')
list=soup.findAll("div", {"class": "NewsItemContent"})[0].findAll("ul")[1].findAll("li")
accel_counties=[]
for item in list:
    for i in (item.findAll("a")[0].text.replace("County","").strip().split('-')):
        accel_counties.append(i)

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

regions=['US',state]
charts=['Tests','Cases','Deaths']

#%%

#All states in one chart
def statecompare(metric,metricname,foci):
    palette=Category20[20]
    colors = itertools.cycle(palette)
    p = figure(title=metricname, x_axis_type='datetime', plot_width=800, plot_height=500,
               tools="pan,wheel_zoom,reset,save")
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

foci=['CA','AZ','FL','GA','TX','NC','LA']
state_cases=statecompare('positiveIncrease_avg','New Cases (7-day avg)',foci)
state_hospitalizations=statecompare('hospitalizedCurrently','Hospitalized',foci)
state_deaths=statecompare('deathIncrease_avg','Deaths (7-day avg)',foci)

state_hospitalizations.x_range=state_cases.x_range
state_deaths.x_range=state_cases.x_range

l=gridplot(
        [[state_cases],
         [state_hospitalizations],
         [state_deaths]]
        )

save(l,filename=fileloc+'\COVID19_National.html')
show(l)

#%% ICU 
source = ColumnDataSource(caData.groupby('Date').sum())
p = figure(x_axis_type='datetime',
           plot_height=400,
           title="CA ICU Capacity",
           toolbar_location='above',
           tools=[HoverTool(tooltips=[
               ('Date','@Date{%F}'),
               ('ICU','@ICU{0,}')
               ],
               formatters={'@Date': 'datetime'})]
        )

p.varea_stack(['ICU','noncovid_icu','icu_available_beds'], x='Date', color=['red','yellow','green'], source=source,
              legend_label=['COVID Cases','Non-COVID Cases','Available Beds'])
p.yaxis.formatter=NumeralTickFormatter(format="0,")

p.legend.location = "top_left"

save(p,filename=fileloc+'\COVID19_State.html')
show(p)

#%% County Gridplot

def countychart(county):
    source=ColumnDataSource(caData[caData.County==county].groupby('Date').sum())
    cases = figure(x_axis_type='datetime',
                   x_range=Range1d(caData.Date.min(),caData.Date.max(),bounds=(caData.Date.min(),caData.Date.max())),
                   y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*10))),
                   title=county,
                   plot_height=300,
                   plot_width=450,
                   toolbar_location='above',
                   tools=["pan,reset,save,wheel_zoom",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Daily New Cases','@positiveIncrease{0,}'),
                   ('7-day average New Cases','@positiveIncrease_avg{0,}')
                   ],
                   formatters={'@Date': 'datetime'})],
                   active_scroll='wheel_zoom',
                   sizing_mode = 'scale_width')       
    cases.line(x='Date', y='positiveIncrease_percap', source=source, color='grey',legend_label='Daily')
    cases.line(x='Date', y='positiveIncrease_avg_percap', source=source, color='blue',width=2, legend_label='7-day average')
    cases.legend.location = "top_left"
    cases.yaxis.axis_label = 'Cases/100k'
    
    deaths = figure(x_axis_type='datetime',
                    y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*10))),
                   plot_height=300,
                   plot_width=450,
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
               plot_width=450,
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
    return layout(cases,deaths,ICU)


save(row(countychart('Sacramento'),countychart('El Dorado'),countychart('Placer'),countychart('Yolo')),filename=fileloc+'\COVID19_Counties.html')
show(row(countychart('Sacramento'),countychart('El Dorado'),countychart('Placer'),countychart('Yolo')))

