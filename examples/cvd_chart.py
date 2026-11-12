"""The last day's cumulative volume delta (CVD) against zero, with pandas and matplotlib.

    pip install "klinelens[pandas]" matplotlib
"""
import matplotlib.pyplot as plt
from klinelens import Client

flow = Client().flow(window="24h", interval="15m").to_pandas()
ax = flow.plot(x="at", y="cumulativeUsd", legend=False, title="Bitcoin CVD, last 24 hours")
ax.axhline(0, linestyle="--", linewidth=1)
ax.set_xlabel("")
ax.set_ylabel("Taker buys minus sells, USD")
plt.tight_layout()
plt.show()
