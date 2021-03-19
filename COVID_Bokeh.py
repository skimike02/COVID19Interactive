# -*- coding: utf-8 -*-
"""
To do:
    Find and add national/state hospitalization data
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
from bs4 import BeautifulSoup
import time
from random import randint
from bokeh.models.widgets import DataTable, TableColumn
import numpy as np


import config

fileloc=config.fileloc
mode=config.mode
base_url=config.base_url
dir_path = os.path.dirname(os.path.abspath(__file__))
filename=dir_path+'\\data.pkl'

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
#url='https://covidtracking.com/api/v1/states/daily.json'
#df=pd.read_json(url)
#logging.info('%s fetched', datetime.datetime.now())
#df['Date']=pd.to_datetime(df.date, format='%Y%m%d', errors='ignore')
#df=df[df['Date']>='2020-03-15']

#CDC Cases and Deaths
try:
    data=pd.read_pickle(filename)
    start=(data.Date.max()+datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    print(f'old data loaded. starting new data load from {start}')
except:
    print('no data found. starting new dataset')
    data=pd.DataFrame()
    start='2020-03-01'
    
def cdc_cases(start):        
    end=(datetime.datetime.now()-datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    enddate=datetime.datetime.strptime(end, '%Y-%m-%d')
    startdate=datetime.datetime.strptime(start, '%Y-%m-%d')
    numdays=(enddate-startdate).days+1
    date_list = [startdate + datetime.timedelta(days=x) for x in range(numdays)]
    df=pd.DataFrame()
    for date in date_list:
        datestring=date.strftime('%Y-%m-%d')
        print(f"fetching data for {date}")
        url=f'https://data.cdc.gov/resource/9mfq-cb36.json?submission_date={datestring}'
        df_day=pd.read_json(url)
        df=df.append(df_day)
    return df

data=data.append(cdc_cases(start))
data['Date']=pd.to_datetime(data.submission_date).dt.date
data.to_pickle(filename)

#National PCR Testing Data
#r=requests.get('https://healthdata.gov/dataset/covid-19-diagnostic-laboratory-testing-pcr-testing-time-series')
#soup = BeautifulSoup(r.content, 'html.parser')
#csv_link=soup.find_all('a',{"class": "btn btn-primary data-link"})[0]['href']
#testing=pd.read_csv(csv_link).pivot(index=['state','date'], columns='overall_outcome', values='new_results_reported').reset_index()
#testing['total_tests']=testing.Inconclusive+testing.Negative+testing.Positive
#testing['Date']=pd.to_datetime(testing.date, format='%Y-%m-%d').dt.date
#data=data.merge(testing,on=['state','Date'],how='left')

testing=pd.read_csv('https://raw.githubusercontent.com/govex/COVID-19/master/data_tables/testing_data/time_series_covid19_US.csv')
testing['date']=pd.to_datetime(testing.date, format='%m/%d/%y').dt.date
testing.sort_values(by=['state','date'],inplace=True)
testing['total_tests']=testing.groupby(['state'])['tests_combined_total'].diff()
testing['Positive']=testing.groupby(['state'])['cases_conf_probable'].diff()
testing.rename(columns={'date':'Date'},inplace=True)
data=data.merge(testing,on=['state','Date'],how='left')


logging.info('%s Fetching state mapping', datetime.datetime.now())
url="https://gist.githubusercontent.com/mshafrir/2646763/raw/8b0dbb93521f5d6889502305335104218454c2bf/states_hash.json"
state_mapping=json.loads(requests.get(url).content)
logging.info('%s fetched', datetime.datetime.now())
#df['STATE']=df.state.map(state_mapping).str.upper()
data['STATE']=data.state.map(state_mapping).str.upper()


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
#url='https://data.ca.gov/dataset/590188d5-8545-4c93-a9a0-e230f0db7290/resource/926fd08f-cc91-4828-af38-bd45de97f8c3/download/statewide_cases.csv'
url='https://data.chhs.ca.gov/dataset/f333528b-4d38-4814-bebb-12db1f10f535/resource/046cdd2b-31e5-4d34-9ed3-b48cdbc4be7a/download/covid19cases_test.csv'
caCases=pd.read_csv(url,delimiter=',')
caCases=caCases[caCases.area_type=='County']
caCases.rename(columns={'area':'county'},inplace=True)
logging.info('%s fetched', datetime.datetime.now())
logging.info('%s Fetching state hospitalization data', datetime.datetime.now())
#url='https://data.ca.gov/dataset/529ac907-6ba1-4cb7-9aae-8966fc96aeef/resource/42d33765-20fd-44b8-a978-b083b7542225/download/hospitals_by_county.csv'
url='https://data.chhs.ca.gov/dataset/2df3e19e-9ee4-42a6-a087-9761f82033f6/resource/47af979d-8685-4981-bced-96a6b79d3ed5/download/covid19hospitalbycounty.csv'
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

#Population
print("Getting populations...")
logging.info('%s Fetching county population data', datetime.datetime.now())
url='https://www2.census.gov/programs-surveys/popest/datasets/2010-2019/counties/totals/co-est2019-alldata.csv'
df4=pd.read_csv(url,delimiter=',',encoding='latin-1')
logging.info('%s fetched', datetime.datetime.now())
statepop=df4.groupby('STNAME').sum().POPESTIMATE2019.to_frame(name="pop")
statepop['STATE']=statepop.index.str.upper()
#df=df.merge(statepop,how='left',on='STATE')
data=data.merge(statepop,how='left',on='STATE')
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
caData['positiveIncrease']=caData['cases']
caData['deathIncrease']=caData['deaths']
caData['noncovid_icu']=caData.ICU_capacity-caData.ICU-caData.icu_available_beds


#fields=['totalTestResultsIncrease','deathIncrease','positiveIncrease']
#for field in fields:
#    df=rolling_7_avg(df,'Date','state',field)
    
fields=['new_case','new_death','Positive','total_tests']
for field in fields:
    data=rolling_7_avg(data,'Date','state',field)

#df['positivity']=df.positiveIncrease_avg/df.totalTestResultsIncrease_avg
#df.loc[df.positivity > 1,'positivity'] = 1

data['positivity']=(data.Positive_avg/data.total_tests_avg).clip(upper=1,lower=0)

fields=['positiveIncrease','deathIncrease']

for field in fields:
    caData=rolling_7_avg(caData,'Date','COUNTY',field)
    
fields=['positiveIncrease','deathIncrease','positiveIncrease_avg','deathIncrease_avg','hospitalized','ICU']
for field in fields:
    caData[field+'_percap']=caData[field]/caData['pop']*100000

#fields=['totalTestResultsIncrease_avg','deathIncrease_avg','positiveIncrease_avg','hospitalizedCurrently']
#for field in fields:
#    df[field+'_percap']=df[field]/df['pop']*100000
    
fields=['new_case','new_death','new_case_avg','new_death_avg']
for field in fields:
    data[field+'_percap']=data[field]/data['pop']*100000

regions=['US',state]
charts=['Tests','Cases','Deaths']

#%% National

#All states in one chart
def statecompare(df,metric,metricname,universe,foci,**kwargs):
    formatter=kwargs.get('format','thousands')
    if formatter=='percent':
        hoverformatter='{0.0%}'
        yformatter="0%"
    else:
        hoverformatter='{0,}'
        yformatter="0,"        
    palette=Category20[20]
    colors = itertools.cycle(palette)
    p = figure(title=metricname, x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
               # y_range=Range1d(0,math.ceil(df[metric].max()), bounds=(0,math.ceil(df[metric].max()*1.5/10)*10)),
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
    grp_list=universe
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
         ('State','@state'),('Date','@Date{%F}'),(metricname,'@'+metric+hoverformatter)],
         formatters={'@Date': 'datetime'})
    p.add_tools(hover)
    p.yaxis.formatter=NumeralTickFormatter(format=yformatter)
    p.legend.location = "top_left"
    p.legend.click_policy="mute"
    p.legend.label_text_font_size="8pt"

    return p

def percap(df,metric,metricname,foci):
    gross=Panel(child=statecompare(df,metric,metricname,universe,foci),title='Gross')
    percap_chart=statecompare(df,metric+'_percap',metricname+' per 100k population',universe,foci)
    percap_chart.hover._property_values['tooltips'][2]=(metricname+' per 100k', '@'+metric+'_percap{0.0}')
    percap_chart.yaxis.formatter=NumeralTickFormatter(format="0.0")
    percap=Panel(child=percap_chart,title='Per 100k')
    return Tabs(tabs=[gross,percap])

padding=Spacer(width=30, height=10, sizing_mode='fixed')


foci=['NY','NJ','CA']

largest_positive_percap = set(data[data.Date>(datetime.datetime.now()+datetime.timedelta(days=-7)).date()][['state','new_case_avg_percap']].groupby('state').sum().nlargest(10,'new_case_avg_percap').index)
#largest_positive_percap = set(df[df.Date>datetime.datetime.now()+datetime.timedelta(days=-7)][['state','positiveIncrease_avg_percap']].groupby('state').sum().nlargest(10,'positiveIncrease_avg_percap').index)
largest_positive = set(data[data.Date>(datetime.datetime.now()+datetime.timedelta(days=-7)).date()][['state','new_case_avg']].groupby('state').sum().nlargest(10,'new_case_avg').index)
#largest_positive = set(df[df.Date>datetime.datetime.now()+datetime.timedelta(days=-7)][['state','positiveIncrease_avg']].groupby('state').sum().nlargest(10,'positiveIncrease_avg').index)
universe = largest_positive_percap.union(largest_positive)
universe.update(foci)

state_cases=percap(data,'new_case_avg','New Cases (7-day avg)',foci)
#state_hospitalizations=percap('hospitalizedCurrently','Hospitalized',foci)
state_deaths=percap(data,'new_death_avg','Deaths (7-day avg)',foci)
positivity=statecompare(data,'positivity','Positivity (7-day avg)',universe,foci)

positivity.y_range=Range1d(0,0.6,bounds=(0,math.ceil(data['positivity'].max()*1.05/10)*10))
positivity.yaxis.formatter=NumeralTickFormatter(format="0%")
positivity.hover._property_values['tooltips'][2]=('Positivity (7-day avg)', '@positivity{0.0%}')

state_deaths.tabs[0].child.y_range=Range1d(0,math.ceil(data[~data.state.isin(['NY','NJ'])].new_death_avg.max()*1.05), bounds=(0,math.ceil(data.new_death_avg.max()*1.5)))

nation_sum=data.groupby('Date').sum()
nation_sum['positivity_avg']=nation_sum.new_case_avg/nation_sum.total_tests_avg
nation_sum['positivity']=nation_sum.new_case/nation_sum.total_tests

source=ColumnDataSource(nation_sum)
nation=figure(title='National', x_axis_type='datetime', plot_width=200, plot_height=400,
               tools="pan,wheel_zoom,reset,save",
                active_scroll='wheel_zoom',
                sizing_mode='stretch_width'
                )
nation.extra_y_ranges = {"deaths": Range1d(start=0, end=data.groupby('Date').sum().new_death.max())}
nation.add_layout(LinearAxis(y_range_name="deaths", axis_label='Deaths'), 'right')
nation.yaxis.formatter=NumeralTickFormatter(format="0,")

nation.line(x='Date', y='new_death_avg', source=source,legend_label = 'Avg Deaths', color='red',y_range_name="deaths",width=2)
nation.line(x='Date', y='new_death', source=source,legend_label = 'Daily Deaths', color='red',y_range_name="deaths",alpha=0.2)
#nation.line(x='Date', y='hospitalizedCurrently', source=source,legend_label = 'Hospitalized', color='orange',width=2)
nation.line(x='Date', y='new_case_avg', source=source,legend_label = 'Avg Cases', color='green',width=2)
nation.line(x='Date', y='new_case', source=source,legend_label = 'Daily Cases', color='green',alpha=0.2)
nation.yaxis[0].axis_label = 'Cases'
nation.legend.location = "top_left"
hover = HoverTool(tooltips =[
     ('Date','@Date{%F}'),
     ('Cases','@new_case{0,}'),
     ('Avg Cases','@new_case_avg{0,}'),
     #('Hospitalized','@hospitalizedCurrently{0,}'),
     ('Deaths','@new_death{0,}'),
     ('Avg Deaths','@new_death_avg{0,}'),
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
                         layout([[nation,
                                  nation_positivity,
                                  padding],
                                 [state_cases,
                                  positivity,
                                  padding],
                                 [#state_hospitalizations,
                                  state_deaths,
                                  padding]],
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

source = ColumnDataSource(data[data.state=='CA'])

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

tests=statechart('total_tests','Tests')
cases=statechart('new_case','Cases')
deaths=statechart('new_death','Deaths')

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
                    #y_range=Range1d(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*1.05/10)*10, bounds=(0,math.ceil(caData[caData.County.isin(counties)].deathIncrease.max()*10))),
                   plot_height=300,
                   #plot_width=cases.width,
                   toolbar_location='above',
                   tools=["pan,reset,save,xwheel_zoom",HoverTool(tooltips=[
                   ('Date','@Date{%F}'),
                   ('Daily New Deaths','@deathIncrease{0,}'),
                   ('7-day average New Deaths','@deathIncrease_avg{0.00}')
                   ],
                   formatters={'@Date': 'datetime'})],
                   active_scroll='xwheel_zoom',
                   sizing_mode = 'stretch_width')        
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
                   sizing_mode = 'stretch_width',
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
#%% Vaccinations
#vacc=pd.read_csv('https://raw.githubusercontent.com/govex/COVID-19/master/data_tables/vaccine_data/raw_data/vaccine_data_us_state_timeline.csv',sep=',')
#vacc['Date']=pd.to_datetime(vacc.date)
#vacc=vacc.merge(statepop,how='left',left_on='Province_State',right_on='STNAME')

#vacc['pct_shipped_administered']=vacc.doses_admin_total/vacc.doses_shipped_total
#vacc['pct_pop_vaccinated']=vacc['doses_admin_total']/vacc['pop']
#vacc['state']=vacc.stabbr

def update_vacc_data():
    try:
        vacc_df=pd.read_pickle(fileloc+'cdc_vaccination.pkl')
        vacc_df.set_index(keys=['Date','Location'],inplace=True)
        new_dataset=False
    except:
        new_dataset=True
        vacc_df=pd.DataFrame()
        print('no existing data. starting new data set')
    url='https://covid.cdc.gov/covid-data-tracker/COVIDData/getAjaxData?id=vaccination_data'
    tmp=requests.get(url).content.decode("utf-8")
    new_data=pd.DataFrame(json.loads(tmp)['vaccination_data'])
    new_data['Date']=pd.to_datetime(new_data.Date)
    new_data.set_index(keys=['Date','Location'],inplace=True)
    if ~new_dataset:
        vacc_df=pd.concat([vacc_df[~vacc_df.index.isin(new_data.index)], new_data])
    else:
        vacc_df=new_data
    vacc_df.reset_index(inplace=True)
    vacc_df.to_pickle(fileloc+'cdc_vaccination.pkl')
    return vacc_df

vacc_data=update_vacc_data()
vacc_data.rename(columns={"Location": "state"}, inplace=True)
vacc_data['pct_dose1']=vacc_data['Administered_Dose1_Per_100K']/100000
vacc_data['pct_dose2']=vacc_data['Administered_Dose2_Per_100K']/100000

#take more recent data format where available
vacc_data['pct_dose1']=(vacc_data['Administered_Dose1_Pop_Pct']/100).fillna(vacc_data['pct_dose1'])
vacc_data['pct_dose2']=(vacc_data['Series_Complete_Pop_Pct']/100).fillna(vacc_data['pct_dose2'])

first_dose_admin=statecompare(vacc_data,'pct_dose1','Percent of population with first dose',universe,['CA'],format='percent')
pop_vaccinated=statecompare(vacc_data,'pct_dose2','Percent of population vaccinated',universe,['CA'],format='percent')

def refresh_cvs_data():
    s=requests.Session()
    url='https://www.cvs.com/immunizations/covid-19-vaccine'
    r=s.get(url)
    
    headers = {
        "referer": 'https://www.cvs.com/immunizations/covid-19-vaccine',
        'sec-ch-ua': '''"Google Chrome";v="89", "Chromium";v="89", ";Not A Brand";v="99"''',
        'sec-ch-ua-mobile': '?0',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': '''Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36}'''
        } 
    url='https://www.cvs.com/immunizations/covid-19-vaccine.vaccine-status.CA.json?vaccineinfo'
    r=s.get(url,headers=headers)
    data=json.loads(r.content)['responsePayloadData']['data']
    df=pd.DataFrame(data['CA'])
    df['store']='CVS'
    df['city']=df.city.str.title()
    return df
    
def make_ra_directory():
    def store_number(name):
        num_start=name.find("#")+1
        num_end=name[num_start:].find(" ")+num_start
        number=name[num_start:num_end]
        return number
    
    base_url='https://www.riteaid.com/locations/'
    state='ca'
    r=requests.get(base_url+state+'.html')
    soup = BeautifulSoup(r.content)
    directory=[]
    for link in soup.find_all('a',attrs={"class": "c-directory-list-content-item-link"}):
        print(f''''fetching {base_url+link['href']}...''')
        r=requests.get(base_url+link['href'])
        soup = BeautifulSoup(r.content)
        city=link.text
        if soup.find('span',attrs={'class':'directory-list-title'})==None:
            name=soup.find('h1',attrs={"class": "Nap-title Text--h1"}).text
            store_num=store_number(name)
            address=soup.find('span',attrs={"class": "c-address-street-1"}).text
            directory.append((store_num, city, address))
        else:
            for store in soup.find_all('div',attrs={'class':'c-location-grid-item'}):
                name=store.find('a',attrs={'itemprop':'url'}).text
                store_num=store_number(name)
                address=store.find('span',attrs={"class": "c-address-street-1"}).text
                directory.append((store_num, city, address))
        time.sleep(randint(1,40)/20)
    ra=pd.DataFrame(directory)
    ra.rename(columns={0:'store_number',1:'city',2:'address'},inplace=True)
    return ra

try:
    ra=pd.read_pickle('rite_aid_stores.pkl')
except:
    ra=make_ra_directory()
    ra.to_pickle('rite_aid_stores.pkl')

#Refresh Rite Aid Data
def refresh_ra_data():
    store_numbers=ra.store_number
    base_url='https://www.riteaid.com/services/ext/v2/vaccine/checkSlots?storeNumber='
    ra_avail=[]
    for i in range(0,len(store_numbers)):
        url=base_url+store_numbers[i]
        print(f'checking store number {i}:{store_numbers[i]}')
        r=requests.get(url)
        try:
            avail=json.loads(r.content)['Data']['slots']['1']
        except:
            avail=False
            print(f'error. response received:{r.content}')
        if avail:
            ra_avail.append(store_numbers[i])
    
    ra['store']='Rite Aid'
    ra['state']='CA'
    ra["status"] = np.where(ra["store_number"].isin(ra_avail), "Available", "Fully Booked")
    return ra

df_cvs=refresh_cvs_data()
df_ra=refresh_ra_data()
df=df_cvs.append(df_ra)
df_avail=df[df.status=='Available']
df_avail.sort_values(by=['city','store','address'])

Columns = [TableColumn(field=Ci, title=Ci.title()) for Ci in df_avail.columns] # bokeh columns
avail_vaccine_locations = DataTable(columns=Columns, source=ColumnDataSource(df_avail)) # bokeh table
now=datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S UTC%z")
chart_info="""
<p><b>California Vaccine Appointment Availability as of {now}</b></p>
<p><a href="https://www.cvs.com/vaccine/intake/store/covid-screener/covid-qns">CVS signup site</a></p>
<p><a href="https://www.riteaid.com/covid-vaccine-apt">Rite Aid signup site</a></p>
"""

vaccinecharts=Panel(child=
                       layout(
                       [[first_dose_admin,pop_vaccinated,Spacer(width=30, height=10, sizing_mode='fixed')],
                        [Div(chart_info)],
                        [avail_vaccine_locations]],
                       sizing_mode='stretch_width'
                       ),
                   title='Vaccination'
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
<p>National and state case and death data pulled from the <a href="https://data.cdc.gov/Case-Surveillance/United-States-COVID-19-Cases-and-Deaths-by-State-o/9mfq-cb36">CDC website</a></p>
<!-- <p>Testing data pulled from <a href="https://healthdata.gov/dataset/covid-19-diagnostic-laboratory-testing-pcr-testing-time-series">HHS website</a></p> --!>
<p>Testing data pulled from <a href="https://github.com/govex/COVID-19/tree/master/data_tables">JHU dataset</a></p> 
<p>CA State and County level data pulled from the <a href="https://data.ca.gov/group/covid-19">CA Open Data Portal</a></p>
<p>Vaccination data pulled from <a href="https://covid.cdc.gov/covid-data-tracker/#vaccinations">CDC Data Tracker</a></p>

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
<a href="https://berthub.eu/articles/posts/reverse-engineering-source-code-of-the-biontech-pfizer-vaccine/">Description of the vaccine source code</a><br>
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
                vaccinecharts,
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

