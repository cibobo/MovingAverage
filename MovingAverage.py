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
    # maximum length of MA queue
    max_MA_len = 10
    # fixed candle interval
    #TODO: use other time interval instead the fixed 1m
    candle_interval = '1m'

    # gradient threashold for the MA long
    grad_MA_long_threadhold = 0

    # Test coins
    symbol_vol = 0
    coin_vol = 0.1

    def __init__(self, symbol, long_interval, short_interval, data_index=4):
        self.symbol = symbol
        self.long_interval = long_interval
        self.short_interval = short_interval
        # data index define which price should be used for MA:
        # 1.open, 2.high, 3.low, 4.close
        self.data_index = data_index

        # queue to save the history MA data
        self.MA_long = deque([0]*self.max_MA_len)
        self.MA_short = deque([0]*self.max_MA_len)

        # data queue to save the history candle data, the length equal to the interval
        self.MA_long_data = deque([0]*self.long_interval)
        self.MA_short_data = deque([0]*self.short_interval)

        # get exchange info for the trading limit
        self.getExchangeInfo()
        print("Min Price is: ", self.minPrice, " \nMin Quantity is: ", self.minQty)

        # trading volumn is used to get the real buy/sell price
        self.trading_vol = {'buy':0,'sell':0}
        self.initTradingVolumn()
        print(self.trading_vol)

        # get the time offset to the server
        self.time_offset = BinanceRestLib.getServerTimeOffset()

        # calculate the first SMA data to start the trading
        # self.initSMA()
        self.initEMA()

        # self.initTestData()

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

    def initRawData(self, need_limit):
        # call API to get the raw data
        raw_data = getHistoryCandle(self.symbol, self.candle_interval, need_limit, self.time_offset)
        # get out only the needed index
        self.data = []
        for i in range(len(raw_data)):
            self.data.append(float(raw_data[i][self.data_index]))

        print(self.data)

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

    def initSMA(self):
        # calculate how much history data are needed at the beginning
        need_limit = self.max_MA_len + self.long_interval - 1
        # # get the history raw data from server
        self.initRawData(need_limit)

        # ----------------- hanlding of SAM Long -------------------------
        # calculate the first SMA in SMA_long
        SMA_long_0 = sum(self.data[:self.long_interval])/self.long_interval
        # add this value into the queue and pop the left default value
        self.MA_long.popleft()
        self.MA_long.append(SMA_long_0)
        # add also the raw data into history candle data queue for the future calculation
        self.MA_long_data = deque(self.data[:self.long_interval])

        # ----------------- hanlding of SAM Short ------------------------
        # calculate the first SMA in SMA_long
        SMA_short_0 = sum(self.data[(self.long_interval-self.short_interval):self.long_interval])/self.short_interval
        # add this value into the queue and pop the left default value
        self.MA_short.popleft()
        self.MA_short.append(SMA_short_0)
        # add also the raw data into history candle data queue for the future calculation
        self.MA_short_data = deque(self.data[(self.long_interval-self.short_interval):self.long_interval])


        # calculate the rest of the SMA with iterator algorithm
        for i in range(1,self.max_MA_len):
            # the new raw data
            new_data = self.data[self.long_interval+i-1]

            self.updateSMA(self.MA_long, self.MA_long_data, self.long_interval, new_data)
            self.updateSMA(self.MA_short, self.MA_short_data, self.short_interval, new_data)

            print(i," th itegration is completed")
            print(self.MA_long)
            print(self.MA_long_data)
            print("Short SMA")
            print(self.MA_short)
            print(self.MA_short_data)

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

    def initEMA(self):
        # calculate how much history data are needed at the beginning
        # the needed data set is calculated by expierent factor k=3.45
        need_limit = self.max_MA_len + math.ceil((self.long_interval+1)*3.45) - 1
        # get the history raw data from server
        self.initRawData(need_limit)

        # calculate the alpha
        self.alpha_long = 2/(self.long_interval+1)
        self.alpha_short = 2/(self.short_interval+1)
        print("Long alpha: ", self.alpha_long, " | Short alpha: ", self.alpha_short)

        # add first data as S_0 into the last position of queue
        self.MA_long[-1] = self.data[0]
        self.MA_short[-1] = self.data[0]

        # calculate recusive for all other EMA value
        for i in range(1,need_limit):
            new_data = self.data[i]
            self.updateEMA(self.MA_long, self.alpha_long, new_data)
            # use all data to calulate short EMA, even if not all of them are needed.
            self.updateEMA(self.MA_short, self.alpha_short, new_data)

            print(i," th itegration is completed")
            print(self.MA_long)
            print("Short SMA")
            print(self.MA_short)

    def updateEMA(self, EMA, alpha, new_data):
        # get the last EMA
        temp = EMA[-1]
        # calculate new EMA value
        temp = alpha*new_data + (1-alpha)*temp
        # add the new calculated SMA into the queue and remove the oldest one
        EMA.popleft()
        EMA.append(temp)

    def initTestData(self):
        file_in = open('C:/Users/Cibobo/Documents/Coins/Python/MA/TestData_ONT_24H.txt', 'r+')
        self.test_data = deque(json.loads(file_in.read()))
        file_in.close()

        self.alpha_long = 2/(self.long_interval+1)
        self.alpha_short = 2/(self.short_interval+1)
        print("Long alpha: ", self.alpha_long, " | Short alpha: ", self.alpha_short)

        need_limit = self.max_MA_len + math.ceil((self.long_interval+1)*3.45) - 1
        first_test_data = self.test_data.popleft()
        self.MA_long[-1] = float(first_test_data[self.data_index])
        self.MA_short[-1] = float(first_test_data[self.data_index])

        for i in range(1,need_limit):
            new_data = float(self.test_data.popleft()[self.data_index])
            self.updateEMA(self.MA_long, self.alpha_long, new_data)
            # use all data to calulate short EMA, even if not all of them are needed.
            self.updateEMA(self.MA_short, self.alpha_short, new_data)

            print(i," th itegration is completed")
            print(self.MA_long)
            print("Short SMA")
            print(self.MA_short)


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
            if self.MA_short[-1] <= self.MA_long[-1]:
                return 'WAIT'
            else:
                return 'INIT'
        
        if state == 'WAIT':
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
        # Checking Rule 1: 
        #   a. MA short through MA long from below; 
        #   b. MA long is moving up
        # if self.MA_short[-1] > self.MA_long[-1] and \
        #     gradientChcck(self.MA_long[-2], self.MA_long[-1], self.grad_MA_long_threadhold): 

        # Checking Rule 2: 
        #   a. MA short will be through MA long from below acoording to a precondition with Linear Spline Interpolation
        #   b. MA long is moving up
        MA_long_pre = 2*self.MA_long[-1] - self.MA_long[-2]
        MA_short_pre = 2*self.MA_short[-1] - self.MA_short[-2]
        if MA_short_pre >= MA_long_pre and \
            gradientChcck(self.MA_long[-2], self.MA_long[-1], self.grad_MA_long_threadhold): 
            return True
        else:
            return False

    def isSellChance(self):
        # Checking Rule 1: if MA short is going done through the MA long from above
        # if self.MA_short[-1] < self.MA_long[-1]:

        # Checking Rule 2: if MA short is begin to going down
        # if self.MA_short[-1] - self.MA_short[-2] < 0:

        # Checking Rule 3: MA short will be through MA long from above acoording to a precondition with Linear Spline Interpolation
        MA_long_pre = 2*self.MA_long[-1] - self.MA_long[-2]
        MA_short_pre = 2*self.MA_short[-1] - self.MA_short[-2]
        if MA_short_pre <= MA_long_pre:
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
        # update MA array and Data array
        # self.updateSMA(self.MA_long, self.MA_long_data, self.long_interval, new_data)
        # self.updateSMA(self.MA_short, self.MA_short_data, self.short_interval, new_data)

        self.updateEMA(self.MA_long, self.alpha_long, new_data)
        self.updateEMA(self.MA_short, self.alpha_short, new_data)

        print("Itegration at time: ", datetime.fromtimestamp(int(response[0][0]/1000)))
        print(self.MA_long)
        # print(self.MA_long_data)
        print("Short MA")
        print(self.MA_short)
        # print(self.MA_short_data)

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
            print("Buy with price: ", price['asks_vol'], "@ ", datetime.now())
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
            
            # file_out_info = str(datetime.fromtimestamp(int(response[0][0]/1000)))
            # file_out_info = file_out_info + " Buy with price: " + str(price['asks_vol']) + "\n"
            # file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            # file_out_info = file_out_info + "Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n"
            # file_out_info = file_out_info + "Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n"
            self.writeLog(datetime.now(), price, "Buy")

        if new_state == 'SELL':
            # # get current price
            # price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)
            # Simulate buy
            self.coin_vol = self.symbol_vol*price['bids_vol']
            self.symbol_vol = 0
            print("Sell with price: ", price['bids_vol'], "@ ", datetime.now())
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))

            # file_out_info = str(datetime.now())
            # file_out_info = file_out_info + "Sell with price: " + str(price['bids_vol']) + "\n"
            # file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            # file_out_info = file_out_info + "Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n"
            # file_out_info = file_out_info + "Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n"
            self.writeLog(datetime.now(), price, "Sell")

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

    def MATradingTest(self):
        current_test_data = self.test_data.popleft()
        new_data = float(current_test_data[self.data_index])
        # update MA array and Data array
        # self.updateSMA(self.MA_long, self.MA_long_data, self.long_interval, new_data)
        # self.updateSMA(self.MA_short, self.MA_short_data, self.short_interval, new_data)

        self.updateEMA(self.MA_long, self.alpha_long, new_data)
        self.updateEMA(self.MA_short, self.alpha_short, new_data)

        print("Itegration at time: ", datetime.fromtimestamp(int(current_test_data[0]/1000)))
        print(self.MA_long)
        print("Short MA")
        print(self.MA_short)

        new_state = self.checkState(self.state)
        print("Current State is: ", new_state)

        price = current_test_data[12]
        if new_state == 'BUY':
            # Simulate buy
            self.symbol_vol = self.coin_vol/float(price['asks_vol'])
            self.coin_vol = 0
            print("Buy with price: ", price['asks_vol'], "@ ", datetime.now())
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
            
            # file_out_info = str(datetime.fromtimestamp(int(current_test_data[0]/1000)))
            # file_out_info = file_out_info + " Buy with price: " + str(price['asks_vol']) + "\n"
            # file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            # file_out_info = file_out_info + "Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n"
            # file_out_info = file_out_info + "Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n"
            self.writeLog(int(current_test_data[0]/1000), price, "Buy")

        if new_state == 'SELL':
            # Simulate Sell
            self.coin_vol = self.symbol_vol*float(price['bids_vol'])
            self.symbol_vol = 0
            print("Sell with price: ", price['bids_vol'], "@ ", datetime.now())
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))

            # file_out_info = str(datetime.fromtimestamp(int(current_test_data[0]/1000)))
            # file_out_info = file_out_info + "Sell with price: " + str(price['bids_vol']) + "\n"
            # file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            # file_out_info = file_out_info + "Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n"
            # file_out_info = file_out_info + "Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n"
            self.writeLog(int(current_test_data[0]/1000), price, "Sell")

        self.state = new_state

    def writeLog(self, timestamp, price, trading_type):
        file_out = open('TradingInfo.log','a')
        file_out.write(str(datetime.fromtimestamp(timestamp)))

        if trading_type == "Buy":
            file_out.write(" Buy with price: " + str(price['asks_vol']) + "\n")
        else:
            file_out.write(" Sell with price: " + str(price['bids_vol']) + "\n")

        file_out.write("Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n")
        file_out.write("Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n")
        file_out.write("Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n")
        file_out.write("\n")
        file_out.close()
        



test = MovingAverage('TRXETH',25,7)

while True:
    test.MATrading()
    # test.MATradingTest()

print(test.symbol_vol)
print(test.coin_vol)
