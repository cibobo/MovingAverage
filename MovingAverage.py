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
 
# convert candle data from 1 min cyclic to N min
def dataConvert1mToNm(data, N):
    convertData = []
    data_length = int(len(data)/N)*N
    print(data_length)
    for i in range(0, data_length, N):
        # init temp with first data element
        temp = data[i]
        for j in range(1,N):
            # get highest as high
            if data[i+j][2] > temp[2]:
                temp[2] = data[i+j][2]
            # get lowest as low
            if data[i+j][3] < temp[3]:
                temp[3] = data[i+j][3]
            # add volumn
            temp[5] += data[i+j][5]
            # add other infors from position 7~11
            temp[7:12] = [sum(x) for x in zip(temp[7:12], data[i+j][7:12])]
        
        # set close price and close time from last element in N min
        temp[4] = data[i+N-1][4]
        temp[6] = data[i+N-1][6]

        # set the current price also fromt the lase minute
        temp[12] = data[i+N-1][12]

        # add the converted data into list
        convertData.append(temp)
        
    return convertData
       

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

    # Diff factor
    diff_factor = 0.00013
    # Stop loss factor
    loss_factor = 1

    def __init__(self, symbol, long_interval, short_interval, isTest, data_index=4):
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

        # parameter to save the current trading state
        self.state = 'INIT'

        if isTest:
            self.initTestData()
        else:
            # calculate the first SMA data to start the trading
            # self.initSMA()
            self.initEMA()
            # Save trading data for further test
            self.initSaveTestData()

        # Delta used to increase the long EMA value, in order to trigger a new buy change after stop loss
        self.delta = 0

        # init log file
        file_out = open('TradingInfo.log','a')
        file_out.write(str(datetime.now())+'\n')
        file_out.close()

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
        file_in = open('C:/Users/Cibobo/Documents/Coins/Python/MA/TestData/TestDataAll/TestData_EOSETH_2018_05_03_07_01', 'r+')
        # self.visual_data = json.loads(file_in.read())
        # self.test_data = deque(self.visual_data)

        # Test with 5 min candle data
        self.visual_data = dataConvert1mToNm(json.loads(file_in.read()), 1)
        self.test_data = deque(self.visual_data)

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

            # print(i," th itegration is completed")
            # print(self.MA_long)
            # print("Short SMA")
            # print(self.MA_short)

        # Data Array for Visulaization
        self.buy_timestamp = []
        self.buy_price = []
        self.sell_timestamp = []
        self.sell_price = []

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
      # if self.MA_short[-1] - self.MA_long[-1] > self.diff_factor*self.MA_long[-1] and \
        #     (self.MA_short[-2] - self.MA_long[-2] < 0 or self.MA_short[-3] - self.MA_long[-3] < 0)  and \
        #     gradientChcck(self.MA_long[-2], self.MA_long[-1], self.grad_MA_long_threadhold): 
        #     print(self.MA_short[-1] - self.MA_long[-1], end=" | ")
        #     print((self.MA_long[-1]-self.MA_long[-2])/self.MA_long[-2], end=" | ")

        # Checking Rule 1 with delta: 
        #   a. MA short through MA long from below; 
        #   b. MA long is moving up
        # if self.MA_short[-1] - (self.MA_long[-1]+self.delta) > 1.0e-08 and \
        #     gradientChcck(self.MA_long[-2], self.MA_long[-1], self.grad_MA_long_threadhold): 
        #     print(self.MA_short[-1] - self.MA_long[-1], end=" | ")
        #     print((self.MA_long[-1]-self.MA_long[-2])/self.MA_long[-2], end=" | ")

        # Checking Rule 2: 
        #   a. MA short will be through MA long from below acoording to a precondition with Linear Spline Interpolation
        #   b. MA long is moving up
        # MA_long_pre = 2*self.MA_long[-1] - self.MA_long[-2]
        # MA_short_pre = 2*self.MA_short[-1] - self.MA_short[-2]
        # if MA_short_pre - MA_long_pre >= 1.0e-08 and \
        #     gradientChcck(self.MA_long[-2], self.MA_long[-1], self.grad_MA_long_threadhold):
        #     print(MA_short_pre - MA_long_pre, end=" | ")
        #     print((self.MA_long[-1]-self.MA_long[-2])/self.MA_long[-2], end=" | ") 
 
        # Checking Rule 3:
        #   a. MA short through MA long from below at t1; 
        #   b. MA long is moving up at t1;
        #   c. MA short is moving up at t1+1
        if self.MA_short[-2] - self.MA_long[-2] > self.diff_factor*self.MA_long[-2] and \
            self.MA_short[-3] - self.MA_long[-3] < 0 and \
            gradientChcck(self.MA_long[-3], self.MA_long[-2], self.grad_MA_long_threadhold) and \
            self.MA_short[-1]>self.MA_short[-2]: 
            print(self.MA_short[-2] - self.MA_long[-2], end=" | ")
            print((self.MA_long[-2]-self.MA_long[-3])/self.MA_long[-3], end=" | ")

            return True
        else:
            return False

    def isSellChance(self):
        # Checking Rule 1: if MA short is going done through the MA long from above
        if self.MA_short[-1] < self.MA_long[-1]:

        # Checking Rule 2: if MA short is begin to going down
        # if self.MA_short[-1] - self.MA_short[-2] < 0:

        # Checking Rule 3: MA short will be through MA long from above acoording to a precondition with Linear Spline Interpolation
        # MA_long_pre = 2*self.MA_long[-1] - self.MA_long[-2]
        # MA_short_pre = 2*self.MA_short[-1] - self.MA_short[-2]
        # if MA_short_pre <= MA_long_pre:
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
        # print(self.MA_long)
        # print(self.MA_long_data)
        # print("Short MA")
        # print(self.MA_short)
        # print(self.MA_short_data)

        # update trading state
        new_state = self.checkState(self.state)
        print("Current State is: ", new_state)

        # get current price
        price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)
        print("Current Price is: ", price)
        
        if new_state == 'BUY':
            # # get current price
            # price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)
            # Simulate buy
            self.symbol_vol = self.coin_vol/price['asks_vol']
            self.coin_vol = 0
            self.buy_price = price['asks_vol']
            print("Buy with price: ", price['asks_vol'], "@ ", datetime.now())
            print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
            
            # file_out_info = str(datetime.fromtimestamp(int(response[0][0]/1000)))
            # file_out_info = file_out_info + " Buy with price: " + str(price['asks_vol']) + "\n"
            # file_out_info = file_out_info + "Calculate balance is: Symbol: " + str(self.symbol_vol) + " | Coin : " + str(self.coin_vol) + "\n"
            # file_out_info = file_out_info + "Last MA long value is: " + str(self.MA_long[-2]) + " | AM short value is: " + str(self.MA_short[-2]) + "\n"
            # file_out_info = file_out_info + "Current MA long value is: " + str(self.MA_long[-1]) + " | AM short value is: " + str(self.MA_short[-1]) + "\n"
            self.writeLog(time.time(), price, "Buy")

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
            self.writeLog(time.time(), price, "Sell")

        if new_state == 'HOLD':
            # create a stop loss condition if it is needed
            # if the current price is less than the last buy price
            if float(price['asks_vol']) < self.buy_price*self.loss_factor:
                print("Special cast: stop loss--------------------")
                self.coin_vol = self.symbol_vol*float(price['bids_vol'])
                self.symbol_vol = 0
                new_state = 'SELL'

                print("Sell with price: ", price['bids_vol'], "@ ", datetime.now())
                print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
                self.writeLog(time.time(), price, "Sell")

        self.state = new_state

        # save all these data to local test
        test_data = response[0]
        test_data.append(price)
        self.saveTestData(test_data)


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

        # print("Itegration at time: ", datetime.fromtimestamp(int(current_test_data[0]/1000)))
        # print(self.MA_long)
        # print("Short MA")
        # print(self.MA_short)

        new_state = self.checkState(self.state)
        # print("Current State is: ", new_state)

        price = current_test_data[12]
        if new_state == 'BUY':
            # Simulate buy
            self.symbol_vol = self.coin_vol/float(price['asks_vol'])
            self.coin_vol = 0
            # print("Buy with price: ", price['asks_vol'], "@ ", datetime.now())
            # print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))
            
            self.writeLog(int(current_test_data[0]/1000), price, "Buy")
            # print("Buy @", int(current_test_data[0]/1000), "with price: ", price['asks_vol'])
            
            # save trading info for visualization
            self.buy_timestamp.append(int(current_test_data[0]/1000))
            self.buy_price.append(float(price['asks_vol']))
            print(price['asks_vol'], end=" | ")
            print(price['asks_vol']-self.MA_long[-1], end=" | ")


        if new_state == 'SELL':
            # Simulate Sell
            self.coin_vol = self.symbol_vol*float(price['bids_vol'])
            self.symbol_vol = 0
            # print("Sell with price: ", price['bids_vol'], "@ ", datetime.now())
            # print("Calculate balance is %s: %f | %s: %f" %(self.symbol[:-3], self.symbol_vol, self.symbol[-3:], self.coin_vol))

            self.writeLog(int(current_test_data[0]/1000), price, "Sell")
            # print("Sell @", int(current_test_data[0]/1000), "with price: ", price['bids_vol'])

            # save trading info for visualization
            self.sell_timestamp.append(int(current_test_data[0]/1000))
            self.sell_price.append(float(price['bids_vol']))
            # print("Price diff: ", float(price['bids_vol'])-self.buy_price[-1])
            print(float(price['bids_vol'])-self.buy_price[-1])
            print()

        if new_state == 'HOLD':
            # create a stop loss condition if it is needed
            # if the current price is less than the last buy price
            if float(price['asks_vol']) < self.buy_price[-1]*self.loss_factor:
                print("Special cast: stop loss")
                self.coin_vol = self.symbol_vol*float(price['bids_vol'])
                self.symbol_vol = 0
                self.writeLog(int(current_test_data[0]/1000), price, "Sell")
                self.sell_timestamp.append(int(current_test_data[0]/1000))
                self.sell_price.append(float(price['bids_vol']))
                new_state = 'SELL'
                # set delta value
                # self.delta = self.MA_short[-1] - self.MA_long[-1]
                # print("Current delta: ", self.delta)
                

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

    # Save trading data for further test
    def initSaveTestData(self):
        self.test_data_save_name = "TestData_" + self.symbol + "_" + datetime.now().strftime("%Y_%m_%d_%H_%M") 
        test_file = open(self.test_data_save_name, 'a')
        test_file.write("[")
        test_file.close()
        self.test_data_save_begin = time.time()

    def saveTestData(self, test_data):
        test_file = open(self.test_data_save_name, 'a')
        
        # create a new log file in every 24 Hour
        if time.time() - self.test_data_save_begin > 86400:
            # add the last data into the old file and close it 
            test_file.write(str(test_data))
            test_file.write("]")
            test_file.close()
            # create a new log
            self.initSaveTestData()
        else:
            test_file.write(str(test_data))
            test_file.write(", ")
            test_file.close()
        


isTest = False
test = MovingAverage('EOSETH',25,7,isTest)

while True:
    test.MATrading()

# while len(test.test_data)>0:
#     test.MATradingTest()

print(test.symbol_vol)
print(test.coin_vol)



