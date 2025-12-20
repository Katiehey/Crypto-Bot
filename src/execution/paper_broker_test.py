from src.execution.paper_broker import PaperBroker

broker = PaperBroker()
df = broker.fetch_ohlcv("BTC/USDT", "1d")

price = df.iloc[-1]["close"]
broker.place_order("BTC/USDT", "buy", amount=0.001, price=price)

print(broker.get_balance())
print(broker.trade_log[-1])
print("Positions:", broker.get_positions())