"""Who was forced out in the last hour, and the biggest single liquidations."""
from klinelens import Client

kl = Client()  # reads KLINELENS_API_KEY
res = kl.liquidations(window="1h", interval="15m", limit=10)
t = res["totals"]
print(f"Last hour: ${t['longUsd']:,.0f} of longs and ${t['shortUsd']:,.0f} of shorts liquidated ({t['count']} in all)")
for e in res["events"]:
    print(f"  {e['at'][11:19]}  {e['side']:5}  ${e['usd']:>12,.0f}  at ${e['price']:,.1f}")
print(f"Requests left today: {res.quota['remaining']}")
