import BinanceRestLib

import json
import time
import math
from datetime import datetime
from collections import deque

def getHistoryCandle(symbol, interval, count, time_offset):
    param = {}
    param['symbol'] = symbol
    param['interval'] = interval
    param['limit'] = count

    # # calculate the begin time of the requried candle history
    # if interval == '1m':
    #     startTime = int((time.time() - 60*count)*1000)
    # elif interval == '5m':
    #     startTime = int((time.time() - 300*count)*1000)
    # else:
    #     print("Not defined interval!!!!")

    # param['startTime'] = startTime + time_offset

    # call rest full API to get the history data
    response = BinanceRestLib.getService('klines', param)
    return response

def saveHistoryCandle(symbol, interval, count):
    time_offset = BinanceRestLib.getServerTimeOffset()
    response = getHistoryCandle(symbol,interval,count,time_offset)
    file_out = open('C:/Users/Cibobo/Documents/Coins/Python/MA/ExampleCandles.txt', 'w+')
    json.dump(response,file_out)
    file_out.close()
    
def calculateSMA(data, interval):
    data_len = len(data)
    # e.g for data_len = 10, interval = 7, only 10-7+1=4 SMA value can be calculated
    SMA = []
    # calculate the first value with data [0] to [interval-1] 
    current_value = sum(data[:interval])/interval
    SMA.append(current_value)
    # calculate the rest with the update formel from interval to data_len-1
    for i in range(interval, data_len):
        # minus the oldest average value
        current_value -= data[i-interval]/interval
        # add the newest average value
        current_value += data[i]/interval
        # save the value to result array
        SMA.append(current_value)

    return SMA 

def gradientChcck(a, b, threadhold):
    if (b-a)/a > threadhold:
        return True
    else:
        return False
        

class MovingAverage(object):
    # maximum length of SMA queue
    max_SMA_len = 10
    # fixed candle interval
    #TODO: use other time interval instead the fixed 1m
    candle_interval = '1m'

    # gradient threashold for the SMA long
    grad_SMA_long_threadhold = 0

    # Test coins
    symbol_vol = 0
    coin_vol = 0.1

    def __init__(self, symbol, long_interval, short_interval, data_index=4):
        self.symbol = symbol
        self.long_interval = long_interval
        self.short_interval = short_interval
        # data index define which price should be used for SMA:
        # 1.open, 2.high, 3.low, 4.close
        self.data_index = data_index

        # queue to save the history SMA data
        self.SMA_long = deque([0]*self.max_SMA_len)
        self.SMA_short = deque([0]*self.max_SMA_len)

        # data queue to save the history candle data, the length equal to the interval
        self.SMA_long_data = deque([0]*self.long_interval)
        self.SMA_short_data = deque([0]*self.short_interval)

        # get exchange info for the trading limit
        self.getExchangeInfo()
        print("Min Price is: ", self.minPrice, " \nMin Quantity is: ", self.minQty)

        # trading volumn is used to get the real buy/sell price
        self.trading_vol = {'buy':0,'sell':0}
        self.initTradingVolumn()
        print(self.trading_vol)

        # get the time offset to the server
        self.time_offset = BinanceRestLib.getServerTimeOffset()

        # get the history raw data from server
        self.initRawData()
        # calculate the first SMA data to start the trading
        self.initSMA()

        # parameter to save the current trading state
        self.state = 'INIT'

        # init log file
        file_out = open('TradingInfo.log','a')
        file_out.write(str(datetime.now())+'\n')
        file_out.close()

        # Test Data
        test_file = open("TestData.txt", 'a')
        test_file.write("[")
        test_file.close()

        # save the current timestamp to keep 1 min cyclic
        self.last_timestamp = time.time()

    def initRawData(self):
        # calculate how much history data are needed at the beginning
        need_limit = self.max_SMA_len + self.long_interval - 1
        # call API to get the raw data
        raw_data = getHistoryCandle(self.symbol, self.candle_interval, need_limit, self.time_offset)
        # get out only the needed index
        self.data = []
        for i in range(len(raw_data)):
            self.data.append(float(raw_data[i][self.data_index]))

        print(self.data)

    def initSMA(self):
        # ----------------- hanlding of SAM Long -------------------------
        # calculate the first SMA in SMA_long
        SMA_long_0 = sum(self.data[:self.long_interval])/self.long_interval
        # add this value into the queue and pop the left default value
        self.SMA_long.popleft()
        self.SMA_long.append(SMA_long_0)
        # add also the raw data into history candle data queue for the future calculation
        self.SMA_long_data = deque(self.data[:self.long_interval])

        # ----------------- hanlding of SAM Short ------------------------
        # calculate the first SMA in SMA_long
        SMA_short_0 = sum(self.data[(self.long_interval-self.short_interval):self.long_interval])/self.short_interval
        # add this value into the queue and pop the left default value
        self.SMA_short.popleft()
        self.SMA_short.append(SMA_short_0)
        # add also the raw data into history candle data queue for the future calculation
        self.SMA_short_data = deque(self.data[(self.long_interval-self.short_interval):self.long_interval])


        # calculate the rest of the SMA with iterator algorithm
        for i in range(1,self.max_SMA_len):
            # the new raw data
            new_data = self.data[self.long_interval+i-1]

            self.updateSMA(self.SMA_long, self.SMA_long_data, self.long_interval, new_data)
            self.updateSMA(self.SMA_short, self.SMA_short_data, self.short_interval, new_data)

            print(i," th itegration is completed")
            print(self.SMA_long)
            print(self.SMA_long_data)
            print("Short SMA")
            print(self.SMA_short)
            print(self.SMA_short_data)

    def initTradingVolumn(self):
        # get the current price with the init trading volumn
        price = BinanceRestLib.getCurrentPriceTicker(self.symbol[:-3], self.symbol[-3:])
        # calculate the needed trading volumn
        self.trading_vol['buy'] = self.coin_vol/price
        self.trading_vol['sell'] = self.coin_vol/price

    def getExchangeInfo(self):
        exchangeInfo = BinanceRestLib.getExchangeInfo()
        # update exchange info in local
        # file_out = open('C:/Users/Cibobo/Documents/Coins/Python/ExchangeInfo.txt','w+')
        # json.dump(exchangeInfo, file_out)
        # file_out.close()

        # get exchange info 
        # get all filters for the target trading symbol
        filters = next(item for item in exchangeInfo['symbols'] if item['symbol'] == str(self.symbol))['filters']
        
        # minimum trading volumn unit
        self.minQty = float(filters[1]['stepSize'])
        
        # minimum trading price unit
        self.minPrice = float(filters[0]['tickSize'])

        # calculate the precise
        self.price_precise = int(-math.log10(self.minPrice))

    def updateSMA(self, SMA, SMA_data, interval, new_data):
        # the last SMA value
        temp = SMA[-1]

        # pop the oldes history data and add the new one
        old_data = SMA_data.popleft()
        SMA_data.append(new_data)

        # minus the fisrt average value and add the new one
        temp -= old_data/interval
        temp += new_data/interval

        # add the new calculated SMA into the queue and remove the oldest one
        SMA.popleft()
        SMA.append(temp)

    def checkState(self, state):
        # define state maschine for the MA state change
        #             init
        #              |
        #        -<-- wait* --<-
        #        |             |
        #       buy <------> sell
        #        |             |
        #        ->-- hold* -->-
        if state == 'INIT':
            if self.SMA_short[-1] <= self.SMA_long[-1]:
                return 'WAIT'
            else:
                return 'INIT'
        
        if state == 'WAIT':
            # If SMA_7 through SMA_25 from under and the gradient of SMA25 is bigger than threshold
            if self.isBuyChance():
                return 'BUY'
            else:
                return 'WAIT'

        if state == 'BUY':
            if self.isSellChance():
                return 'SELL'
            else:
                return 'HOLD'

        if state == 'HOLD':
            if self.isSellChance():
                return 'SELL'
            else:
                return 'HOLD'
        
        if state == 'SELL':
            if self.isBuyChance():
                return 'BUY'
            else:
                return 'WAIT'

    def isBuyChance(self):
        if self.SMA_short[-1] > self.SMA_long[-1] and \
            gradientChcck(self.SMA_long[-2], self.SMA_long[-1], self.grad_SMA_long_threadhold): 
        # grad_long = self.SMA_long[-1]-self.SMA_long[-2]
        # grad_short = self.SMA_short[-1]-self.SMA_short[-2]
        # # if the short SMA is going near to the long SMA, and has a bigger slope than the long SMA
        # if (self.SMA_long[-1] - self.SMA_short[-1])/self.SMA_short[-1] > 0.1  and \
        #     grad_short > grad_long and \
        #     gradientChcck(self.SMA_long[-2], self.SMA_long[-1], self.grad_SMA_long_threadhold):
            return True
        else:
            return False

    def isSellChance(self):
        # if self.SMA_short[-1] < self.SMA_long[-1]:
        # if the SMA short is begin to going down
        if self.SMA_short[-1] - self.SMA_short[-2] < 0:
            return True
        else:
            return False

    def MATrading(self):
        # calculate how much time should be waiting for
        time_diff = time.time() - self.last_timestamp
        # wait for the next candle cyclic
        time.sleep(60-time_diff)

        # get the current candle date
        response = getHistoryCandle(self.symbol, self.candle_interval, 1, self.time_offset)
        print(response)

        new_data = float(response[0][self.data_index])
        # update SMA array and Data array
        self.updateSMA(self.SMA_long, self.SMA_long_data, self.long_interval, new_data)
        self.updateSMA(self.SMA_short, self.SMA_short_data, self.short_interval, new_data)

        print("Itegration at time: ", datetime.fromtimestamp(int(response[0][0]/1000)))
        # print(self.SMA_long)
        # print(self.SMA_long_data)
        # print("Short SMA")
        # print(self.SMA_short)
        # print(self.SMA_short_data)

        # update trading state
        new_state = self.checkState(self.state)
        print("Current State is: ", new_state)

        # get current price
        price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)

        if new_state == 'BUY':
            # # get current price
            # price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)
            # Simulate buy
            self.symbol_vol = self.coin_vol/price['asks_vol']
            self.coin_vol = 0
            print("Buy with price: ", price['asks_vol'])
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
            
            file_out_info = str(datetime.fromtimestamp(int(response[0][0]/1000)))
            file_out_info = file_out_info + " Buy with price: " + str(price['asks_vol']) + "\n"
            file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            self.writeLog(file_out_info)

        if new_state == 'SELL':
            # # get current price
            # price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)
            # Simulate buy
            self.coin_vol = self.symbol_vol*price['bids_vol']
            self.symbol_vol = 0
            print("Sell with price: ", price['bids_vol'])
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))

            file_out_info = str(datetime.fromtimestamp(int(response[0][0]/1000)))
            file_out_info = file_out_info + "Sell with price: " + str(price['bids_vol']) + "\n"
            file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            self.writeLog(file_out_info)

        self.state = new_state

        # save all these data to local test
        test_data = response[0]
        test_data.append(price)
        test_file = open("TestData.txt", 'a')
        test_file.write(str(test_data))
        test_file.write(", ")
        test_file.close()


        # save the timestamp after all operations are executed
        self.last_timestamp = time.time()

    def writeLog(self, info):
        file_out = open('TradingInfo.log','a')
        file_out.write(info + "\n")
        file_out.close()
        



test = MovingAverage('ONTETH',25,7)

while True:
    test.MATrading()

print(test.symbol_vol)
print(test.coin_vol)
