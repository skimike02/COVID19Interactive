# -*- coding: utf-8 -*-
"""
To do:
    County Charts
        -Add county hospitalization/ICU charts
        -Add mouseover to ICU charts
"""
#%% Config
import pandas as pd
from bokeh.plotting import figure, show, save, output_file
from bokeh.models import (NumeralTickFormatter,ColumnDataSource,HoverTool, Range1d,Panel,Tabs,Div,
                          LinearAxis, GeoJSONDataSource, LinearColorMapper, ColorBar)
from bokeh.layouts import layout,row,Spacer
from bokeh.palettes import Category20,OrRd9
import itertools
import datetime
import math
import requests
import json
import geopandas as gpd
import jinja2
import logging
import os

import config

fileloc=config.fileloc
mode=config.mode
base_url=config.base_url
dir_path = os.path.dirname(os.path.abspath(__file__))


if not os.path.exists(config.log_dir):
    os.makedirs(config.log_dir)
if not os.path.exists(config.log_dir+config.log_file):
    with open(config.log_dir+config.log_file,'w+'): pass
logging.basicConfig(filename=config.log_dir+config.log_file, level=logging.INFO)
logging.info('%s COVID Dashboard Update Started', datetime.datetime.now())

state='CA'
counties=['Sacramento','El Dorado','Placer','Yolo']
#%% Data Imports
#Tests and National Stats
print("Fetching national statistics...")
logging.info('%s Fetching national statistics', datetime.datetime.now())
url='https://covidtracking.com/api/v1/states/daily.json'
df=pd.read_json(url)
logging.info('%s fetched', datetime.datetime.now())
df['Date']=pd.to_datetime(df.date, format='%Y%m%d', errors='ignore')
df=df[df['Date']>='2020-03-15']

logging.info('%s Fetching state mapping', datetime.datetime.now())
url="https://gist.githubusercontent.com/mshafrir/2646763/raw/8b0dbb93521f5d6889502305335104218454c2bf/states_hash.json"
state_mapping=json.loads(requests.get(url).content)
logging.info('%s fetched', datetime.datetime.now())
df['STATE']=df.state.map(state_mapping).str.upper()

def rolling_7_avg(df,date,group,field):
    newname=field+'_avg'
    df.sort_values(by=[group,date],inplace=True)
    #averages=df.groupby(group).rolling(7,min_periods=7)[field].mean().reset_index()[field]
    averages=df.reset_index().set_index(date).groupby(group).rolling(7,min_periods=7)[field].mean().reset_index()
    averages.rename(columns={field:newname},inplace=True)
    return df.merge(averages,on=[group,date])

#CA Data
print("Getting state case data...")
logging.info('%s Fetching state data', datetime.datetime.now())
url='https://data.ca.gov/dataset/590188d5-8545-4c93-a9a0-e230f0db7290/resource/926fd08f-cc91-4828-af38-bd45de97f8c3/download/statewide_cases.csv'
caCases=pd.read_csv(url,delimiter=',')
logging.info('%s fetched', datetime.datetime.now())
logging.info('%s Fetching state hospitalization data', datetime.datetime.now())
url='https://data.ca.gov/dataset/529ac907-6ba1-4cb7-9aae-8966fc96aeef/resource/42d33765-20fd-44b8-a978-b083b7542225/download/hospitals_by_county.csv'
caHosp=pd.read_csv(url,delimiter=',')
logging.info('%s fetched', datetime.datetime.now())
caHosp = caHosp[pd.notnull(caHosp['todays_date'])]
caHosp = caHosp[pd.notnull(caHosp['county'])]
caData=caCases.merge(caHosp, how='left', left_on=['county','date'], right_on=['county','todays_date'])
caData['Date']=pd.to_datetime(caData['date'], format='%Y-%m-%d')
caData['COUNTY']=caData['county'].str.upper()
caData.rename(columns={'county':'County'}, inplace=True)
caData.drop(columns=['date','todays_date'], inplace=True)

#hospital capacity
print("Getting hospital capacity...")
logging.info('%s Fetching hospital capacity data', datetime.datetime.now())
url='https://data.chhs.ca.gov/datastore/dump/0997fa8e-ef7c-43f2-8b9a-94672935fa60?q=&sort=_id+asc&fields=FACID%2CFACNAME%2CFAC_FDR%2CBED_CAPACITY_TYPE%2CBED_CAPACITY%2CCOUNTY_NAME&filters=%7B%7D&format=csv'
df3=pd.read_csv(url,delimiter=',')
logging.info('%s fetched', datetime.datetime.now())
hospital_capacity=df3[df3['FAC_FDR']=='GENERAL ACUTE CARE HOSPITAL'].groupby('COUNTY_NAME').sum()['BED_CAPACITY']
ICU_capacity=df3[(df3['FAC_FDR']=='GENERAL ACUTE CARE HOSPITAL')&(df3['BED_CAPACITY_TYPE']=='INTENSIVE CARE')].groupby('COUNTY_NAME').sum()['BED_CAPACITY']
hospital_capacity.rename("hospital_capacity",inplace=True)
ICU_capacity.rename("ICU_capacity",inplace=True)
caData=caData.merge(hospital_capacity,left_on='COUNTY', right_index=True, how='left').merge(ICU_capacity,left_on='COUNTY', right_index=True, how='left')

#County Population
print("Getting county populations...")
logging.info('%s Fetching county population data', datetime.datetime.now())
url='https://www2.census.gov/programs-surveys/popest/datasets/2010-2019/counties/totals/co-est2019-alldata.csv'
df4=pd.read_csv(url,delimiter=',',encoding='latin-1')
logging.info('%s fetched', datetime.datetime.now())
statepop=df4.groupby('STNAME').sum().POPESTIMATE2019.to_frame(name="pop")
statepop['STATE']=statepop.index.str.upper()
df=df.merge(statepop,how='left',on='STATE')
df4=df4[(df4['STATE']==6)&(df4['COUNTY']>0)]
df4['county']=df4['CTYNAME'].str.replace(' County','').str.upper()
df4=df4[['county','POPESTIMATE2019']]
caData=caData.merge(df4, left_on='COUNTY',right_on='county')
caData.rename(columns={"POPESTIMATE2019": "pop"},inplace=True)

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


fields=['totalTestResultsIncrease','deathIncrease','positiveIncrease']

for field in fields:
    df=rolling_7_avg(df,'Date','state',field)

df['positivity']=df.positiveIncrease_avg/df.totalTestResultsIncrease_avg
df.loc[df.positivity > 1,'positivity'] = 1

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
    largest_positive_percap = set(df[df.Date>datetime.datetime.now()+datetime.timedelta(days=-7)][['state','positiveIncrease_avg_percap']].groupby('state').sum().nlargest(10,'positiveIncrease_avg_percap').index)
    largest_positive = set(df[df.Date>datetime.datetime.now()+datetime.timedelta(days=-7)][['state','positiveIncrease_avg']].groupby('state').sum().nlargest(10,'positiveIncrease_avg').index)
    grp_list = largest_positive_percap.union(largest_positive)
    grp_list.update(['NY','NJ','CA'])
    grp_list=sorted(list(grp_list))
    
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

foci=['NY','NJ','CA']

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

#%% Maps

def get_geodatasource(gdf):    
    json_data = json.dumps(json.loads(gdf.to_json()))
    return GeoJSONDataSource(geojson = json_data)

shapefile = os.path.join(dir_path,'Counties/cb_2018_us_county_500k.shp')
gdf = gpd.read_file(shapefile)[['NAME','geometry']]
merged = gdf.merge(caData[caData.Date==caData.Date.max()], left_on = 'NAME', right_on = 'County', how = 'left').drop(columns='Date')
palette=OrRd9[::-1]


def plot_map(df,metric,high,low,**kwargs):
    global palette
    source=get_geodatasource(merged)
    tools = 'wheel_zoom,pan,reset,save'
    color_mapper = LinearColorMapper(palette=palette, low = low, high = high)
    p = figure(
        title=kwargs.get('title','Chart'), tools=tools, plot_width=500,
        x_axis_location=None, y_axis_location=None,
        tooltips=[("Name", "@NAME"), (kwargs.get('label','metric'), "@"+metric+'{0.00}')],
        sizing_mode='scale_width',
        )
    
    p.grid.grid_line_color = None
    p.hover.point_policy = "follow_mouse"
    p.patches(xs='xs', ys='ys', source=source,
              fill_color={'field': metric, 'transform': color_mapper},
              fill_alpha=0.7, line_color="grey", line_width=0.5)
    color_bar = ColorBar(color_mapper=color_mapper,
                         label_standoff=8,
                         height=20,
                         location=(0,0),
                         orientation='horizontal')
    p.add_layout(color_bar, 'below')
    return(p)

data_as_of=caData.Date.max().strftime("%b %d")
hospitalization_map=plot_map(merged,'hospital_usage',30,0,title='Hospitalizations as of '+data_as_of,label='% hospitalization usage')
cases_map=plot_map(merged,'positiveIncrease_avg_percap',30,0,title='Daily New Cases (7-day avg) as of '+data_as_of,label='daily new cases per 100k')
deaths_map=plot_map(merged,'deathIncrease_avg_percap',1,0,title='Daily New Deaths (7-day avg) as of '+data_as_of,label='daily new deaths per 100k')
icu_map=plot_map(merged,'ICU_usage',30,0,title='ICU Usage as of '+data_as_of,label='% ICU Usage')

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
               tools=['save', HoverTool(tooltips=[
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
           tools=['save',HoverTool(tooltips=[
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
                         layout([[tests,cases,deaths],[hospitalizations,icu,Spacer(width=30, height=10, sizing_mode='fixed')],
                                 [cases_map,hospitalization_map,icu_map,deaths_map,Spacer(width=30, height=10, sizing_mode='fixed')]],
                         sizing_mode='scale_width',
                         ),
                      title='California')

#%% Counties

def countychart(county):
    source=ColumnDataSource(caData[caData.County==county].groupby('Date').sum())
    cases = figure(x_axis_type='datetime',
                   x_range=Range1d(caData.Date.min(),caData.Date.max(),bounds=(caData.Date.min()-datetime.timedelta(days=5),caData.Date.max()+datetime.timedelta(days=5))),
                   y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].positiveIncrease_percap.max()*10))),
                   title=county,
                   plot_height=300,
                   plot_width=100,
                   sizing_mode='stretch_width',
                   toolbar_location='above',
                   tools=["pan,reset,save,wheel_zoom",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('7-day avg New Cases/100k','@positiveIncrease_avg_percap{0.00}'),
                   ('Daily New Cases','@positiveIncrease{0,}'),
                   ('7-day avg New Cases','@positiveIncrease_avg{0,}'),
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
                   ('7-day average New Deaths','@deathIncrease_avg{0.00}')
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
                       [[countychart('Sacramento'),countychart('Riverside'),countychart('Placer'),countychart('Yolo'),Spacer(width=30, height=10, sizing_mode='fixed')]],
                       sizing_mode='stretch_width'
                       ),
                   title='Region'
                )
#%% Regional Order
def region_map():
    Northern_California= ['Del Norte', 'Glenn', 'Humboldt', 'Lake', 'Lassen', 'Mendocino', 'Modoc', 'Shasta', 'Siskiyou', 'Tehama', 'Trinity']
    Bay_Area= ['Alameda', 'Contra Costa', 'Marin', 'Monterey', 'Napa', 'San Francisco', 'San Mateo', 'Santa Clara', 'Santa Cruz', 'Solano', 'Sonoma']
    Greater_Sacramento= ['Alpine', 'Amador', 'Butte', 'Colusa', 'El Dorado', 'Nevada', 'Placer', 'Plumas', 'Sacramento', 'Sierra', 'Sutter', 'Yolo', 'Yuba']
    San_Joaquin_Valley= ['Calaveras', 'Fresno', 'Kern', 'Kings', 'Madera', 'Mariposa', 'Merced', 'San Benito', 'San Joaquin', 'Stanislaus', 'Tulare', 'Tuolumne']
    Southern_California= ['Imperial', 'Inyo', 'Los Angeles', 'Mono', 'Orange', 'Riverside', 'San Bernardino', 'San Diego', 'San Luis Obispo', 'Santa Barbara', 'Ventura']
    Regions={'Northern_California':Northern_California,'Bay_Area':Bay_Area,'Greater_Sacramento':Greater_Sacramento,
             'San_Joaquin_Valley':San_Joaquin_Valley,'Southern_California':Southern_California}
    tmp=[]
    for region in Regions:
        for county in Regions[region]:
            tmp.append([county,region])
    regions_df=pd.DataFrame(tmp,columns=['County','region'])
    orig_num_records=len(caData)
    tmp2=caData.merge(regions_df,how='left',on='County')
    new_Num_records=len(tmp2)
    if orig_num_records==new_Num_records:
        return tmp2
    else:
        print("Unexpected cartesian when joining regions to data. Join canceled.")
        return caData
        
caData=region_map()
icu_data=caData.groupby(by=['Date','region']).sum()[['icu_available_beds','ICU_capacity','noncovid_icu','icu_suspected_covid_patients','icu_covid_confirmed_patients']]
icu_data['avail_percent']=icu_data['icu_available_beds']/icu_data['ICU_capacity']
icu_data['noncovid_percent']=icu_data['noncovid_icu']/icu_data['ICU_capacity']
icu_data['covid_percent']=(icu_data['icu_suspected_covid_patients']+icu_data['icu_covid_confirmed_patients'])/icu_data['ICU_capacity']
icu_data.reset_index(inplace=True)

def regioncompare(metric,metricname):
    palette=Category20[20]
    colors = itertools.cycle(palette)
    p = figure(title=metricname, x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
                y_range=Range1d(0,math.ceil(icu_data[metric].max()), bounds=(0,math.ceil(icu_data[metric].max()*1.5/10)*10)),
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
    grp_list = icu_data.region.unique()
    grp_list=sorted(list(grp_list))
    
    lines={}
    for i,color in zip(range(len(grp_list)),colors):
        source = ColumnDataSource(
        data={'Date':icu_data.loc[icu_data.region == grp_list[i]].Date,
               'Region':icu_data.loc[icu_data.region == grp_list[i]].region,
               metric:icu_data.loc[icu_data.region == grp_list[i]][metric]})
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
                muted = False)
    hover = HoverTool(tooltips =[
         ('Region','@Region'),('Date','@Date{%F}'),(metricname,'@'+metric+'{0.0%}')],
         formatters={'@Date': 'datetime'})
    p.add_tools(hover)
    p.yaxis.formatter=NumeralTickFormatter(format="0%")
    p.legend.location = "top_left"
    p.legend.click_policy="mute"
    p.legend.label_text_font_size="8pt"

    return p

#show(regioncompare('avail_percent','available'))

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
print("saving file to "+fileloc+'COVID19.html')
logging.info('%s saving file to %sCOVID19.html', datetime.datetime.now(), fileloc)

output_file(fileloc+'COVID19.html')
templateLoader = jinja2.FileSystemLoader(searchpath="./")
templateEnv = jinja2.Environment(loader=templateLoader)
TEMPLATE_FILE = os.path.join(dir_path,"home.html")
with open(TEMPLATE_FILE) as file_:
    template=jinja2.Template(file_.read())
save(page,title='COVID19',template=template)

