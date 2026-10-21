"""Request bounded low-latency BLE parameters only for this gateway's peers."""
import asyncio
import re


def connections(text):
    return {(match[1].upper(), int(match[2])) for match in re.finditer(
        r'\bLE\s+([0-9A-Fa-f:]{17})\s+handle\s+(\d+)\s+state\s+\d+', text)}


async def command(*args):
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), 3)
        return process.returncode, out.decode(errors='replace'), err.decode(errors='replace')
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def maintain_low_latency(relay, sky_address, logger):
    applied = set()
    failures = {}
    while True:
        try:
            code, out, err = await command('hcitool', 'con')
            if code:
                raise RuntimeError(err[:100])
            peers = connections(out)
            applied.intersection_update(peers)
            failures = {key:value for key,value in failures.items() if key in peers}
            selected = {sky_address.upper(), getattr(relay, 'upstream_address', '')}
            for address, handle in sorted(peers):
                key = address, handle
                if address not in selected or key in applied or failures.get(key,0) >= 3:
                    continue
                # Units: interval 1.25 ms, timeout 10 ms. No overclock or MTU tricks.
                code, out, err = await command('hcitool','lecup','--handle',str(handle),
                    '--min','6','--max','12','--latency','0','--timeout','400')
                logger('ble_low_latency_request', address=address, handle=handle,
                       interval_ms=[7.5,15], accepted=code==0, error=err[:120])
                if code==0:
                    applied.add(key)
                else:
                    failures[key] = failures.get(key,0)+1
        except Exception as exc:
            # A tuning failure must not interrupt working UART traffic.
            logger('ble_low_latency_unavailable', reason=str(exc)[:120])
        await asyncio.sleep(2)
