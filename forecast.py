from cloudant import Cloudant
from flask import Flask, render_template, request, jsonify, make_response
import cf_deployment_tracker
import os
import io
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import requests
import numpy as np
import arrow

# Emit Bluemix deployment event
cf_deployment_tracker.track()

app = Flask(__name__)

# On Bluemix, get the port number from the environment variable PORT
# When running this app on the local machine, default the port to 8000
port = int(os.getenv('PORT', 8000))

#Detta görs för varje tidpunkt. Ta värdena och lägg dem i rätt ordning efter name_list.
def get_values(forecast, name_list):
    values = []
    for name in name_list:
        new_value = next(item['values'][0] for item in forecast if item["name"] == name)
        values.append(new_value)
    return values

#Returnerar hur många dagar det är från nu till time.
def rel_dag(time):
    nyss = arrow.now('CET')
    tiden = arrow.get(time)
    dagsskillnad = tiden.date()-nyss.date()
    return dagsskillnad.days

#Returnerar ett diagram, från vilken kolumn, dagar från nu och den stora prognosmatrisen.
def get_chart(column, day, forecast_array): #day = 0-9
    chart_col = np.where(forecast_array[0]==column)[0] #Hitta numret på kolumnen med prognosvärdena
    day_column = np.where(forecast_array[0]=='day')[0] #Hitta dagskolumn
    hour_column = np.where(forecast_array[0]=='hour')[0] #Hitta timkolumn
    hours_that_day = np.where(forecast_array[:,day_column]==str(day))[0] #Ta fram alla rader som gäller den aktuella dagen
    chart_data = forecast_array[hours_that_day,[hour_column,chart_col]] #Ta fram timmar och värden för dessa timmar
    values = [float(item) for item in chart_data[1]]
    #Skapa diagrammet
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    axis.plot(list(chart_data[0]),list(values))
    #print(list(chart_data[0]),list(values))
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    canvas.print_png(output)
    response = make_response(output.getvalue())
    response.mimetype = 'image/png'
    return response

'''Varje prognospunkt ser ut så här i json. Kallas fc i koden.
[{'name': 'spp', 'levelType': 'hl', 'level': 0, 'unit': 'percent', 'values': [-9]}, {'name': 'pcat', 'levelType': 'hl', 'level': 0, 'unit': 'category', 'values': [0]}, {'name': 'pmin', 'levelType': 'hl', 'level': 0, 'unit': 'kg/m2/h', 'values': [0.0]}, {'name': 'pmean', 'levelType': 'hl', 'level': 0, 'unit': 'kg/m2/h', 'values': [0.0]}, {'name': 'pmax', 'levelType': 'hl', 'level': 0, 'unit': 'kg/m2/h', 'values': [0.0]}, {'name': 'pmedian', 'levelType': 'hl', 'level': 0, 'unit': 'kg/m2/h', 'values': [0.0]}, {'name': 'tcc_mean', 'levelType': 'hl', 'level': 0, 'unit': 'octas', 'values': [1]}, {'name': 'lcc_mean', 'levelType': 'hl', 'level': 0, 'unit': 'octas', 'values': [1]}, {'name': 'mcc_mean', 'levelType': 'hl', 'level': 0, 'unit': 'octas', 'values': [0]}, {'name': 'hcc_mean', 'levelType': 'hl', 'level': 0, 'unit': 'octas', 'values': [0]}, {'name': 'msl', 'levelType': 'hmsl', 'level': 0, 'unit': 'hPa', 'values': [1011.5]}, {'name': 't', 'levelType': 'hl', 'level': 2, 'unit': 'Cel', 'values': [23.7]}, {'name': 'vis', 'levelType': 'hl', 'level': 2, 'unit': 'km', 'values': [32.6]}, {'name': 'wd', 'levelType': 'hl', 'level': 10, 'unit': 'degree', 'values': [197]}, {'name': 'ws', 'levelType': 'hl', 'level': 10, 'unit': 'm/s', 'values': [3.3]}, {'name': 'r', 'levelType': 'hl', 'level': 2, 'unit': 'percent', 'values': [74]}, {'name': 'tstm', 'levelType': 'hl', 'level': 0, 'unit': 'percent', 'values': [7]}, {'name': 'gust', 'levelType': 'hl', 'level': 10, 'unit': 'm/s', 'values': [7.0]}, {'name': 'Wsymb2', 'levelType': 'hl', 'level': 0, 'unit': 'category', 'values': [1]}]

name och det första i listan values behålls. Dessutom finns det en tidsstämpel som plockas upp. Förutsätt att man vill
ha allt i CET-tidszonen.
'''

#Returnerar en np.array med prognoser och tidskolumner för den geometriska punkten lat,lon.
def init(lat='55.589979', lon='12.943137'):

    url = 'https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point/lon/'+lon+'/lat/'+lat+'/data.json'
    r = requests.get(url)

    #Skapa en temporär lista fc av alla prognoser i json-resultatet
    fc = [item['parameters'] for item in r.json()['timeSeries']]

    #Skapa en lista över alla sorters värden man får, typ t för temperatur.
    name_list = [item['name'] for item in fc[0]]

    #Skapa den stora numpy-arrayen som ska heta forecast_array och som först består
    #bara av name_list.
    forecast_array = np.array(name_list)
    for forecast in fc:
        hourly_fc = get_values(forecast, name_list)
        #Lägg på rad för rad med prognospunkter
        forecast_array = np.vstack((forecast_array,hourly_fc))

    #Skapa kolumn med rubriken 'time' och alla tider i arrow-format
    time_list = [arrow.get(item['validTime']).to('CET') for item in r.json()['timeSeries']]
    time_list = np.array(time_list)
    time_list = np.append('time', time_list)
    time_list = np.expand_dims(time_list, axis=1)
    forecast_array = np.hstack((forecast_array,time_list))

    #Skapa en kolumn med alla klockslag (i CET) i formatet 07, 12, 23 etc.
    hour_list = [arrow.get(item).format('HH') for item in time_list[1:,:].T[0]]
    hour_list = np.array(hour_list)
    hour_list = np.append('hour', hour_list)
    hour_list = np.expand_dims(hour_list, axis=1)
    forecast_array = np.hstack((forecast_array,hour_list))

    #Skapa en kolumn med hur många dagar bort som prognosraden är.
    day_list = [rel_dag(item) for item in time_list[1:,:].T[0]]
    day_list = np.array(day_list)
    day_list = np.append('day', day_list)
    day_list = np.expand_dims(day_list, axis=1)
    forecast_array = np.hstack((forecast_array,day_list))

    return forecast_array

#Route för att generera själva sidan
@app.route('/')
def withimage():
    return render_template('forecast.html')

#Route för att generera bilden
@app.route('/forecast.png')
def fc():
    forecast_array = init() #Skapa prognosmatrisen
    response = get_chart('t', 0, forecast_array) #Typ av prognos, antal dagar från idag, hela prognosmatrisen
    #Response är själva diagrammet som kan renderas direkt i sid-mallen.
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True)
