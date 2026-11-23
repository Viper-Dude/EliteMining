r"""Before/after comparison of Commodity Market searches (live network, dev tool).

Usage (from the repo root):
    app\.venv\Scripts\python.exe scripts\compare_market_search.py --save before
    ... make the change ...
    app\.venv\Scripts\python.exe scripts\compare_market_search.py --save after
    app\.venv\Scripts\python.exe scripts\compare_market_search.py --compare before after

Or in one go: --compare before   (runs a fresh search set and compares it to "before").
Add --quick for a smaller set (Painite only, Sol and Galaxy-Wide).

Runs the same backend calls the Mining and Trade tabs use. Works on a temporary
copy of app/data/marketplace_cache.db so the searches never write to the real one.
Snapshots are saved outside the repo (default: <temp>/elitemining_market_compare).
Prices are live: run "before" and "after" close together.
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from marketplace_api import MarketplaceAPI  # noqa: E402

DEFAULT_DIR = Path(tempfile.gettempdir()) / 'elitemining_market_compare'
CACHE_SRC = ROOT / 'app' / 'data' / 'marketplace_cache.db'

LOCATIONS = [('near', 'Sol'), ('near', 'Colonia'), ('near', 'HIP 67282'), ('galaxy', 'Sol')]
AGES = ['8 hours', 'Any']
MINING = ['Painite', 'Platinum']
TRADE = ['Gold']
GALAXY_LIMIT = 250

# Same table the Trade tab uses (_convert_age_to_days in commodity_market_tab.py).
TRADE_DAYS = {'Any': 30, '1 hour': 2, '8 hours': 2, '16 hours': 2, '1 day': 2, '2 days': 3}


def mining_days(age):
    """Mining tab window: today 30; after step 2 the shared MarketplaceAPI helper."""
    helper = getattr(MarketplaceAPI, 'convert_age_to_days', None)
    return helper(age) if helper else 30


def search_list(quick):
    mining = MINING[:1] if quick else MINING
    trade = [] if quick else TRADE
    locations = [LOCATIONS[0], LOCATIONS[3]] if quick else LOCATIONS
    for kind, system in locations:
        for age in AGES:
            for tab, commodities in (('mining', mining), ('trade', trade)):
                for commodity in commodities:
                    for buy_mode in (False, True):
                        yield tab, kind, system, age, commodity, buy_mode


def run_search(tab, kind, system, age, commodity, buy_mode):
    days = mining_days(age) if tab == 'mining' else TRADE_DAYS.get(age, 1)
    exclude_carriers = False
    if kind == 'galaxy':
        fn = MarketplaceAPI.search_sellers_galaxy_wide if buy_mode else MarketplaceAPI.search_buyers_galaxy_wide
        results = fn(commodity, days, exclude_carriers)
    else:
        fn = MarketplaceAPI.search_sellers if buy_mode else MarketplaceAPI.search_buyers
        results = fn(commodity, system, None, days, exclude_carriers)
    raw_count = len(results)
    results = MarketplaceAPI.filter_results(results, 'All', age, exclude_carriers, False, buy_mode)
    order_by = 'Distance'
    if kind == 'galaxy':
        results = MarketplaceAPI.prepare_galaxy_results(results, order_by, buy_mode, GALAXY_LIMIT, system)
    else:
        results = MarketplaceAPI.sort_results(results, order_by, buy_mode)
    return raw_count, results


def row_key(row):
    return str(row.get('marketId') or f"{row.get('systemName')}|{row.get('stationName')}")


def snapshot(quick):
    tmp = tempfile.mkdtemp(prefix='market_compare_')
    cache_copy = Path(tmp) / 'marketplace_cache.db'
    if CACHE_SRC.exists():
        shutil.copy2(CACHE_SRC, cache_copy)
        MarketplaceAPI.EDDN_CACHE_PATH = str(cache_copy)
    else:
        print('Note: no dev cache found; the EDDN cache source is skipped.')
    out = {}
    for spec in search_list(quick):
        name = ' | '.join([spec[0], spec[1], spec[2], spec[3], spec[4], 'buy' if spec[5] else 'sell'])
        start = time.time()
        try:
            raw_count, rows = run_search(*spec)
            error = None
        except Exception as exc:
            raw_count, rows, error = 0, [], str(exc)
        elapsed = round(time.time() - start, 2)
        out[name] = {
            'seconds': elapsed, 'raw': raw_count, 'error': error,
            'rows': {row_key(r): {
                'station': r.get('stationName'), 'system': r.get('systemName'),
                'price': r.get('buyPrice' if spec[5] else 'sellPrice'),
                'updated': r.get('updatedAt'), 'distance': r.get('distance'),
            } for r in rows},
        }
        print(f"{name}: {len(rows)} rows (raw {raw_count}), {elapsed}s" + (f"  ERROR {error}" if error else ''))
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def compare(before, after):
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if not b or not a:
            print(f"{name}: only in {'before' if b else 'after'}")
            continue
        added = sorted(set(a['rows']) - set(b['rows']))
        lost = sorted(set(b['rows']) - set(a['rows']))
        print(f"{name}: rows {len(b['rows'])} -> {len(a['rows'])}, "
              f"time {b['seconds']}s -> {a['seconds']}s, +{len(added)} / -{len(lost)}")
        if a.get('error') or b.get('error'):
            print(f"    errors: before={b.get('error')} after={a.get('error')}")
        for label, keys, source in (('added', added, a), ('lost', lost, b)):
            for key in keys[:10]:
                r = source['rows'][key]
                print(f"    {label}: {r['station']} ({r['system']}) {r['price']} cr, updated {r['updated']}")
            if len(keys) > 10:
                print(f"    ... {len(keys) - 10} more {label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--save', metavar='NAME', help='run the searches and save the snapshot')
    parser.add_argument('--compare', nargs='+', metavar='NAME',
                        help='one name: run now and compare with it; two names: compare saved snapshots')
    parser.add_argument('--dir', default=str(DEFAULT_DIR), help='snapshot folder (keep it outside the repo)')
    parser.add_argument('--quick', action='store_true', help='smaller search set')
    args = parser.parse_args()
    folder = Path(args.dir)
    if ROOT in folder.resolve().parents or folder.resolve() == ROOT:
        parser.error('snapshot folder must be outside the repo')
    folder.mkdir(parents=True, exist_ok=True)

    def path(name):
        return folder / f'{name}.json'

    if args.save:
        path(args.save).write_text(json.dumps(snapshot(args.quick)), encoding='utf-8')
        print(f'Saved {path(args.save)}')
    elif args.compare:
        if len(args.compare) == 1:
            after = snapshot(args.quick)
        elif len(args.compare) == 2:
            after = json.loads(path(args.compare[1]).read_text(encoding='utf-8'))
        else:
            parser.error('--compare takes one or two names')
        compare(json.loads(path(args.compare[0]).read_text(encoding='utf-8')), after)
    else:
        parser.error('use --save or --compare')


if __name__ == '__main__':
    main()
