
import base64
import datetime
import json
import random
import time

import ed25519
import requests


API_KEY = ''
API_SECERT = ''

MARKET_SYMBOL = 'SOL_USDC'
MAX_VOLUME = 1000000
EVERY_SWAP_AMOUNT = 0.4


def sign_access(operate_method,argument,timetick,window_value):
    build_string = 'instruction=%s&' % (operate_method)
    sorted_keys = sorted(argument.keys())

    for key in sorted_keys:
        build_string += '%s=%s&' % (key,argument.get(key))

    build_string = build_string[:-1] + '&timestamp=%d&window=%d' % (timetick,window_value)
    private_key = ed25519.SigningKey(base64.b64decode(API_SECERT))
    signature = private_key.sign(build_string.encode())
    
    return base64.b64encode(signature).decode()

def build_access(http_method,operate_method,path,argument):
    timetick = int(time.time() * 1000)
    window_value = 5000

    if operate_method:
        headers = {
            'X-Timestamp': str(timetick),
            'X-Window': str(window_value),
            'X-API-Key': API_KEY,
            'X-Signature': sign_access(operate_method,argument,timetick,window_value),
        }
    else:
        headers = {}

    url = 'https://api.backpack.exchange/' + path
    http_method = http_method.lower()

    if http_method == 'get':
        if argument:
            sorted_keys = sorted(argument.keys())
            url += '?'
            for key in sorted_keys:
                url += '%s=%s&' % (key,argument.get(key))

            url = url[:-1]
            
        resp = requests.get(url,headers=headers,timeout=window_value)
        return resp.text
    elif http_method == 'post':
        resp = requests.post(url,headers=headers,timeout=window_value,json=argument)
        return resp.text
    elif http_method == 'delete':
        resp = requests.delete(url,headers=headers,timeout=window_value,json=argument)
        return resp.text

def get_symbol():
    return json.loads(build_access('get','','api/v1/markets',{}))

def get_new_price():
    price_history = json.loads(build_access('get','','api/v1/klines',{'symbol':MARKET_SYMBOL,'interval':'1m'}))
    price = float(price_history[-1]['close'])
    return price

def get_history(symbol):
    all_history = []
    index = 0

    while True:
        history_data = json.loads(build_access('get','orderHistoryQueryAll','wapi/v1/history/orders',{'symbol':symbol,'offset':index,'limit':1000}))
        index += 1000
        if history_data:
            all_history += history_data
        else:
            break

    return all_history

def get_total_volume(symbol):
    all_history = get_history(symbol)
    total_volume = 0.0

    for history_info in all_history:
        if not history_info['status'] == 'Filled':
            continue
        
        total_volume += round(float(history_info['price']) * float(history_info['quantity']),3)

    return total_volume

def get_assert():
    return json.loads(build_access('get','balanceQuery','api/v1/capital',{}))

def get_deposit_address(blockchain):
    return build_access('get','depositAddressQuery','wapi/v1/capital/deposit/address',{'blockchain':blockchain})

def get_orders(symbols):
    return json.loads(build_access('get','orderQueryAll','api/v1/orders',{'symbol':symbols}))

def cancel_orders(symbols):
    return build_access('delete','orderCancelAll','api/v1/orders',{'symbol':symbols})

def execute_order(symbol,price,amount,is_buy):
    '''
    https://docs.backpack.exchange/#tag/Order/operation/execute_order
        {
            "clientId": 0,
            "orderType": "Market",
            "postOnly": true,
            "price": "string",
            "quantity": "string",
            "quoteQuantity": "string",
            "selfTradePrevention": "RejectTaker",
            "side": "Bid",
            "symbol": "string",
            "timeInForce": "GTC",
            "triggerPrice": "string"
        }
    '''

    if is_buy:
        side_type = 'Bid'
    else:
        side_type = 'Ask'

    resp = build_access('post','orderExecute','api/v1/order',{
            'orderType':'Limit',
            'side': side_type,
            'price': price,
            'symbol': symbol,
            'quantity': str(amount),
        })

    if resp == 'Insufficient funds':
        raise
    print(resp)
    return json.loads(resp)

def calcu_usdc_to_sol(price,usdc_amount):
    sol_amount = round((usdc_amount / price) * 0.99,2)  #  保留两位小数

    return sol_amount

def get_sol_balance():
    balance_list = get_assert()
    sol_info = balance_list.get('SOL',{})
    print(sol_info)
    sol_balance = float(sol_info.get('available',0)) + float(sol_info.get('locked',0))

    return sol_balance

def get_usdc_balance():
    balance_list = get_assert()
    usdc_info = balance_list.get('USDC',{})
    usdc_balance = float(usdc_info.get('available',0))

    return usdc_balance

def get_total_sol_balance():
    balance_list = get_assert()
    usdc_info = balance_list.get('USDC',{})
    usdc_balance = float(usdc_info.get('available',0)) + float(usdc_info.get('locked',0))
    price = get_new_price()
    sol_info = balance_list.get('SOL',{})
    sol_balance = float(sol_info.get('available',0)) + float(sol_info.get('locked',0)) + calcu_usdc_to_sol(price,usdc_balance)
    
    return sol_balance

def buy_all_sol():
    usdc_balance = get_usdc_balance()

    if usdc_balance > 1:  #  因为没有了sol,就需要把所有usdc换成sol
        price = get_new_price()
        swap_to_sol_amount = calcu_usdc_to_sol(price,usdc_balance)
        print(execute_order(MARKET_SYMBOL,price,swap_to_sol_amount,True))

if __name__ == '__main__':
    #total_volume = get_total_volume(MARKET_SYMBOL)
    total_balance = get_total_sol_balance()
    need_exit = False
    
    #while total_volume < MAX_VOLUME:  #  这种读取所有历史数据统计成交量的方法会越刷越慢
    while total_balance >= 0.1:   #  总资产小于0.1 sol就不刷了
        for index in range(10):
            try:  #  尝试卖出sol换usdc
                price = get_new_price()
                print(datetime.datetime.now(),price,'Buy')
                amount = round(random.uniform(0.1,EVERY_SWAP_AMOUNT),2)
                print(execute_order(MARKET_SYMBOL,price,amount,False))
            except:  #  sol没钱了
                print(datetime.datetime.now(),'Cancel Order')
                cancel_orders(MARKET_SYMBOL)

                try:
                    print(datetime.datetime.now(),'Buy Sol')
                    buy_all_sol()
                    #time.sleep(3)
                    #solana_balance = get_sol_balance()

                    #if solana_balance < EVERY_SWAP_AMOUNT:
                    #    need_exit = True
                    #    break

                    continue
                except:
                    pass

            #time.sleep(random.randint(2,6))

            try:  #  尝试用usdc买入sol
                price = get_new_price()
                print(datetime.datetime.now(),price,'Sell')
                amount = round(random.uniform(0.1,EVERY_SWAP_AMOUNT),2)
                print(execute_order(MARKET_SYMBOL,price,amount,True))
            except:
                pass

            #time.sleep(random.randint(2,6))
            #time.sleep(random.randint(10,60))

        if need_exit:
            break

        #total_volume = get_total_volume(MARKET_SYMBOL)
        #print(datetime.datetime.now(),'Total Volume',total_volume)
        total_balance = get_total_sol_balance()
        print(datetime.datetime.now(),'Total Balance',total_balance,'(Sol)')

    if get_orders(MARKET_SYMBOL):
        cancel_orders(MARKET_SYMBOL)

    buy_all_sol()


