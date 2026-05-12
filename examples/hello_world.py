"""Hello World demo for PyTo Code."""

import asyncio

from pyto_code import run


async def main():
    result = await run("Write a Python hello world program and run it")
    print("Result:", result)


if __name__ == "__main__":
    asyncio.run(main())
