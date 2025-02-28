
:::{note}
The library is fully async and methods that perform IO need to be run inside an async coroutine.

The main entry point for the API is {meth}`~kasa.Discover.discover` and
{meth}`~kasa.Discover.discover_single` which return Device objects.
Most newer devices require your TP-Link cloud username and password, but this can be omitted for older devices.

:::{important}
All of your code needs to run inside the same event loop so only call `asyncio.run` once.
:::

Code examples assume you are following them inside `asyncio REPL`:
```
    $ python -m asyncio
```
Or the code is running inside an async function:
```py
import asyncio
from kasa import Discover

async def main():
    dev = await Discover.discover_single("127.0.0.1", username="un@example.com", password="pw")
    await dev.turn_on()
    await dev.update()

if __name__ == "__main__":
    asyncio.run(main())
```

::::{include} ../creds_hashing.md

:::
