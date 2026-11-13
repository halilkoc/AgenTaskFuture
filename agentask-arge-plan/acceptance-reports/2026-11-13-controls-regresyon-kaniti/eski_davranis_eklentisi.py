"""Kanıt: düzeltme öncesi geri yazma davranışı (yalnız görünen metin karşılaştırılır)."""
from agentask.application import controls as c
async def _restore(self, driver, cid, before):
    await driver.fill(cid, before.value or "")
    await driver.settle()
    return ((await driver.state(cid)).value or "") == (before.value or "")
c.AutocompleteAdapter._restore = _restore
