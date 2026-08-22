import random
import math
import statistics
import sys

# ── CONFIG ────────────────────────────────────────────────────────────────────
TICK_RATE = 10  # ticks per second (each tick = 100ms), matches the real game's setInterval(tick, 100)
MAX_TICKS = 50000  # ~83 minutes max
DEBUG_INTERVAL = 1000  # print state every N ticks (only in verbose mode)

# ── COSTS ────────────────────────────────────────────────────────────────────
# Mirrors bolo-bolo-game.html exactly (function names/formulas kept 1:1 for auditability).

def farm_cost(G):
    return math.floor(3 * math.pow(1.35, G['farmLv']))

def sibi_cost(G):
    return math.floor(10 * math.pow(1.25, G['sibiLv'] - 1))

def ibu_cost(G):
    return math.floor(10 * math.pow(1.2, math.floor(G['ibu'] / 5)))

def munu_mult(G):
    return 2 if G['nimaId'] == 'anarcho' else 1

def sila_mult(G):
    if G['nimaId'] == 'franco': return 3
    if G['nimaId'] == 'hash': return 2
    return 1

def record_nima_tally(G, action):
    """Call before mutating state for farm/sibi/host/munu — only counts
    toward nima detection once identity-relevant choice exists (tutStage>=2)
    and more than one option was actually affordable at this moment."""
    if G['tutStage'] >= 2 and len(identity_options_available(G)) >= 2:
        G['nimaTally'][action] += 1

def identity_options_available(G):
    """Which of {farm, sibi, host, munu} are affordable right now — used to
    tell a genuine choice (multiple viable) from a forced default (only one
    viable), so nima detection only counts real preference, not filler taken
    because nothing else was affordable at that moment."""
    costs_sibi = G['tutStage'] >= 3
    opts = []
    if costs_sibi:
        if G['sibi'] >= farm_cost(G): opts.append('farm')
    else:
        if G['kodu'] >= farm_cost(G): opts.append('farm')
    if G['kodu'] >= sibi_cost(G): opts.append('sibi')
    if G['tutStage'] >= 2 and G['feno'] == 0 and G['kodu'] >= 10: opts.append('host')
    if G['tutStage'] >= 3 and G['sibi'] >= 8: opts.append('munu')
    return opts

# ── NIMA ──────────────────────────────────────────────────────────────────────

NIMAS = {
    'agro':    {'bonus': 'koduRate x2'},
    'craft':   {'bonus': 'sibiRate +0.3'},
    'eco':     {'bonus': 'koduMax 400'},
    'anarcho': {'bonus': 'munu x2'},
    'franco':  {'bonus': 'silaMax 150'},
    'dada':    {'bonus': 'random'},
    'tao':     {'bonus': 'auto kodu +2/6s'},
    'hash':    {'bonus': 'traveller bonus'},
}

def assign_nima(G):
    f, si, h, m = (G['nimaTally']['farm'], G['nimaTally']['sibi'],
                   G['nimaTally']['host'], G['nimaTally']['munu'])
    total = f + si + h + m
    if G['chosenNima']:
        nid = G['chosenNima']
    elif total == 0:
        nid = 'tao'
    elif f >= si and f >= h and f >= m:
        nid = 'agro' if f > total * 0.6 else 'eco'
    elif si >= f and si >= h and si >= m:
        nid = 'craft'
    elif h >= f and h >= si and h >= m:
        nid = 'franco' if h > total * 0.5 else 'hash'
    elif m >= f and m >= si and m >= h:
        nid = 'anarcho'
    else:
        nid = 'dada'

    G['nimaId'] = nid
    if nid == 'agro':    G['koduRate'] *= 2
    if nid == 'craft':   G['sibiRate'] = max(G['sibiRate'], 0.3)
    if nid == 'eco':     G['koduMax'] = max(G['koduMax'], 400)
    if nid == 'franco':  G['silaMax'] = 150
    if nid == 'hash':    G['silaMax'] = max(G['silaMax'], 80)
    if nid == 'tao':     G['koduRate'] = max(G['koduRate'], 0.5)
    if nid == 'dada':    G['koduRate'] += random.random() * 0.8
    G['phase'] = 2
    G['tutStage'] = 5
    G['machineRevealAt'] = G['tick'] + 30
    G['exchangeRevealAt'] = G['tick'] + 70
    return nid

# ── GAME STATE ───────────────────────────────────────────────────────────────

def new_game(chosen_nima=None):
    G = {
        'tick': 0, 'phase': 1, 'tutStage': 0,
        'chosenNima': chosen_nima,
        'ibu': 5, 'ibuMax': 50,
        'kodu': 20, 'koduMax': 150, 'koduRate': 0.5,
        'sibi': 4, 'sibiMax': 100, 'sibiRate': 0,
        'munu': 0, 'munuMax': 500,
        'sila': 0, 'silaMax': 50,
        'feno': 0,
        'farmLv': 1, 'sibiLv': 1,
        'tricoCount': 0, 'tegaCount': 0, 'sumiCount': 0, 'sumiBuilt': 0, 'asaDone': False,
        'bolosFree': 0,
        'travelersHosted': 0,
        'machineGrip': 95,
        'bandits': [],
        'lastBanditTick': 0,
        'lastEventTick': 0,
        'lastTravelerTick': 0,
        'harvestPenalty': 0,
        'sumiSeceding': False,
        'nimaId': None,
        'farmActions': 0, 'sibiActions': 0, 'hostActions': 0, 'munuActions': 0,
        # Separate tally used ONLY for nima detection — counts an action only
        # when it was a genuine choice (another identity action was also
        # affordable at that moment), not when it was the sole viable option.
        # farmActions/etc above are untouched and still drive the tutorial
        # stage gates exactly as before.
        'nimaTally': {'farm': 0, 'sibi': 0, 'host': 0, 'munu': 0},
        'machineRevealAt': None, 'exchangeRevealAt': None,
        'lastAutoHostTick': 0,
        'events': [],  # log of notable events (tick, label)
        # ── metrics, for balance/pacing analysis (not part of the real game) ──
        'metrics': {
            'milestones': {},       # name -> tick first reached
            'actionCounts': {},     # action -> count (manual clicks only)
            'autoHostFires': 0,     # passive host-equivalent firings, not a "click"
            'negativeEvents': {'harvest': 0, 'travelerTrouble': 0, 'ibuSplit': 0,
                                'sumiSecession': 0, 'sumiLost': 0, 'banditSpawn': 0,
                                'starvationDeaths': 0, 'ibuDrift': 0},
            'idleTicks': 0,         # ticks where the AI had no valid action to take
            'koduZeroTicks': 0,     # ticks spent at 0 food
            'totalActions': 0,
            'peakIbu': 5,           # highest population reached
            # ── visitor-layer metrics (prototype, unused unless run_once_social) ──
            'visitorMilestones': [],  # (tick, label) for ally/hostile transitions
            'reconciled': 0,
            'expelled': 0,
        },
        # visitor-layer state — dead/inert weight for the baseline sim, only
        # touched by process_visitors/process_grudges (run_once_social path),
        # so existing baseline runs are byte-for-byte unaffected.
        'visitors': None,
        'lastVisitTick': -10**9,
    }
    G['map'] = ['machine'] * 64
    G['map'][0] = 'yours'
    return G

def mark_milestone(G, name):
    if name not in G['metrics']['milestones']:
        G['metrics']['milestones'][name] = G['tick']

# ── ACTION EXECUTION ─────────────────────────────────────────────────────────
# Every branch mirrors actions() in bolo-bolo-game.html exactly.

def do_action(G, action):
    tut = G['tutStage']

    if action == 'farm':
        c = farm_cost(G)
        if tut == 0:
            if G['kodu'] < 5: return False
            G['kodu'] -= 5
            G['koduRate'] += 0.2
            G['farmActions'] += 1
            check_tutorial(G)
            return True
        # Staged currency: kodu until munu-spread unlocks (tutStage 3), sibi after.
        costs_sibi = tut >= 3
        pool = G['sibi'] if costs_sibi else G['kodu']
        if pool < c: return False
        record_nima_tally(G, 'farm')
        if costs_sibi: G['sibi'] -= c
        else: G['kodu'] -= c
        G['farmLv'] += 1
        G['koduRate'] += 0.45 if G['nimaId'] == 'agro' else 0.22
        G['koduMax'] += 30
        G['farmActions'] += 1
        check_tutorial(G)
        return True

    elif action == 'sibi':
        c = sibi_cost(G)
        if G['kodu'] < c: return False
        record_nima_tally(G, 'sibi')
        G['kodu'] -= c
        G['sibiLv'] += 1
        gain = 4 + G['sibiLv']
        G['sibi'] += gain
        G['sibiMax'] += 25
        if G['nimaId'] == 'craft': G['sibiRate'] += 0.08
        G['sibiActions'] += 1
        check_tutorial(G)
        return True

    elif action == 'ibu':
        c = ibu_cost(G)
        if G['kodu'] < c or G['ibu'] >= G['ibuMax']: return False
        G['kodu'] -= c
        G['ibu'] = min(G['ibu'] + 1, G['ibuMax'])
        G['koduRate'] += 0.04
        check_phase(G)
        return True

    elif action == 'host':
        if G['kodu'] < 10: return False
        record_nima_tally(G, 'host')
        G['kodu'] -= 10
        G['sila'] = min(G['sila'] + sila_mult(G) * 2, G['silaMax'])
        G['munu'] = min(G['munu'] + munu_mult(G) * 3, G['munuMax'])
        G['travelersHosted'] += 1
        G['hostActions'] += 1
        if G['nimaId'] == 'hash' and random.random() < 0.4:
            G['kodu'] += 8
        check_tutorial(G)
        check_phase(G)
        return True

    elif action == 'munu':
        if G['sibi'] < 5: return False
        record_nima_tally(G, 'munu')
        G['sibi'] -= 5
        G['munu'] = min(G['munu'] + munu_mult(G) * 5, G['munuMax'])
        G['munuActions'] += 1
        check_tutorial(G)
        check_phase(G)
        return True

    elif action == 'trico':
        if G['munu'] < 30: return False
        G['munu'] -= 30
        G['tricoCount'] += 1
        for i in range(len(G['map'])):
            if G['map'][i] == 'machine':
                G['map'][i] = 'trico'
                break
        G['machineGrip'] = max(10, G['machineGrip'] - 3)
        mark_milestone(G, 'firstTrico')
        check_phase(G)
        return True

    elif action == 'feno':
        if G['munu'] < 20: return False
        G['munu'] -= 20
        G['feno'] += 1
        G['koduRate'] += 0.1
        G['sibiRate'] += 0.04
        mark_milestone(G, 'firstFeno')
        return True

    elif action == 'tega':
        if G['tricoCount'] < 5: return False
        G['tegaCount'] += 1
        G['tricoCount'] -= 5
        G['machineGrip'] = max(5, G['machineGrip'] - 15)
        G['ibuMax'] += 100
        G['koduMax'] += 500
        # A tega is "twenty bolos" joining your network — that should bring
        # real people, not just raise the population cap.
        G['ibu'] = min(G['ibu'] + 20, G['ibuMax'])
        added = 0
        for i in range(len(G['map'])):
            if added >= 10: break
            if G['map'][i] == 'machine':
                G['map'][i] = 'allied'
                added += 1
        mark_milestone(G, 'firstTega')
        check_phase(G)
        return True

    elif action == 'sumi':
        if G['tegaCount'] < 3: return False
        G['sumiCount'] += 1
        G['sumiBuilt'] += 1
        G['tegaCount'] -= 3
        G['machineGrip'] = max(2, G['machineGrip'] - 25)
        # A sumi is a whole autonomous region joining — a much bigger influx.
        G['ibu'] = min(G['ibu'] + 50, G['ibuMax'])
        freed = 0
        for i in range(len(G['map'])):
            if G['map'][i] == 'machine' and random.random() < 0.5:
                G['map'][i] = 'free'
                freed += 1
        mark_milestone(G, 'firstSumi')
        check_phase(G)
        return True

    elif action == 'asa':
        if G['sumiBuilt'] < 3 or G['asaDone']: return False
        G['asaDone'] = True
        G['machineGrip'] = 0
        G['map'] = ['free'] * 64
        G['map'][0] = 'yours'
        mark_milestone(G, 'win')
        return True

    elif action == 'yaka':
        if G['munu'] < 10 or not G['bandits']: return False
        G['munu'] -= 10
        # Real game resolves this 2.5s later via setTimeout; the sim treats it
        # as instant since nothing else can intervene on the same bandit in a
        # single-threaded tick loop.
        G['bandits'].pop()
        mark_milestone(G, 'firstYaka')
        return True

    elif action == 'absorb':
        if not G['bandits'] or G['kodu'] < 25: return False
        G['kodu'] -= 25
        G['bandits'].pop()
        gained = 2 + random.randint(0, 2)
        G['ibu'] = min(G['ibu'] + gained, G['ibuMax'])
        G['munu'] = min(G['munu'] + 2, G['munuMax'])
        mark_milestone(G, 'firstAbsorb')
        return True

    return False

# ── TUTORIAL / PHASE CHECKS ──────────────────────────────────────────────────

def check_tutorial(G):
    s = G['tutStage']
    if s == 0 and G['farmActions'] >= 1:
        G['tutStage'] = 1
        mark_milestone(G, 'stage1_sibiRevealed')
    if s == 1 and G['ibu'] >= 8 and G['sibi'] >= 8:
        G['tutStage'] = 2
        mark_milestone(G, 'stage2_hospitalityRevealed')
        # nimaTally naturally starts empty here — the pre-hospitality bootstrap
        # never touched it (host/munu weren't even options yet), so it can't
        # swamp the ratio the way raw farmActions/sibiActions used to.
    if s == 2 and G['hostActions'] >= 1:
        G['tutStage'] = 3
        mark_milestone(G, 'stage3_munuRevealed')
    # Gate on genuine-choice signal gathered (nimaTally total) when possible —
    # but a player (or AI) who always does "the one obviously best thing"
    # never generates a "multiple options were viable" moment by definition,
    # so tally growth can legitimately stall forever for a very consistent
    # playstyle. That must never become a soft-lock: after a generous grace
    # period, fall back to the original bar regardless of tally size (a
    # near-empty tally still resolves sensibly via assign_nima's total==0 ->
    # 'tao' branch — "no clear preference showed" is itself a valid signal).
    tally_total = sum(G['nimaTally'].values())
    original_bar_met = G['munu'] >= 15 or G['travelersHosted'] >= 3
    dwell = G['tick'] - G['metrics']['milestones'].get('stage3_munuRevealed', 0)
    if s == 3 and original_bar_met and (tally_total >= 6 or dwell >= 900):
        G['tutStage'] = 4
        nid = assign_nima(G)
        mark_milestone(G, 'stage4_nimaAssigned')
        G['events'].append((G['tick'], f"NIMA ASSIGNED: {nid}"))
    if s == 6 and G['phase'] >= 3:
        G['tutStage'] = 7

def check_phase(G):
    if G['phase'] == 1:
        check_tutorial(G)
    if G['phase'] == 2 and G['tricoCount'] >= 3:
        G['phase'] = 3
        mark_milestone(G, 'phase3')
        G['events'].append((G['tick'], f"PHASE 3 UNLOCKED (tricoCount={G['tricoCount']})"))

# ── TICK ─────────────────────────────────────────────────────────────────────

def tick(G):
    G['tick'] += 1
    t = G['tick']
    M = G['metrics']

    # Passive production
    effective_rate = G['koduRate'] * 0.4 if G['harvestPenalty'] > 0 else G['koduRate']
    G['kodu'] = min(G['kodu'] + effective_rate * 0.1, G['koduMax'])
    G['sibi'] = min(G['sibi'] + G['sibiRate'] * 0.1, G['sibiMax'])

    # Tao passive bonus — flat trickle (was G.ibu*0.2, uncapped scaling; fixed to flat +2)
    if G['nimaId'] == 'tao' and t % 60 == 0:
        G['kodu'] = min(G['kodu'] + 2, G['koduMax'])

    # Network self-sustaining production (trico/tega/sumi feed themselves)
    if G['tricoCount'] > 0:
        G['munu'] = min(G['munu'] + G['tricoCount'] * 0.015, G['munuMax'])
    if G['tegaCount'] > 0:
        tega_mult = 0.4 if G['harvestPenalty'] > 0 else 1
        G['kodu'] = min(G['kodu'] + G['tegaCount'] * 0.2 * tega_mult, G['koduMax'])
        G['sibi'] = min(G['sibi'] + G['tegaCount'] * 0.05, G['sibiMax'])
    if G['sumiCount'] > 0:
        G['munu'] = min(G['munu'] + G['sumiCount'] * 0.1, G['munuMax'])

    # Dada random events (3 branches: kodu / munu / sibi)
    if G['nimaId'] == 'dada' and t % 90 == 0:
        r = random.random()
        if r < 0.30:   G['kodu'] = min(G['kodu'] + 15, G['koduMax'])
        elif r < 0.55: G['munu'] = min(G['munu'] + munu_mult(G) * 8, G['munuMax'])
        elif r < 0.75: G['sibi'] = min(G['sibi'] + 8, G['sibiMax'])

    # Munu decay (phase 1 only)
    if G['phase'] == 1 and t % 150 == 0 and G['munu'] > 0:
        G['munu'] = max(0, G['munu'] - 0.2)

    # Kodu shortage — ibu leave
    if G['kodu'] <= 0:
        G['kodu'] = 0
        M['koduZeroTicks'] += 1
        if t % 60 == 0 and G['ibu'] > 2:
            G['ibu'] = max(2, G['ibu'] - 1)
            G['koduRate'] = max(0.1, G['koduRate'] - 0.04)
            M['negativeEvents']['starvationDeaths'] += 1

    # Ibu drift — quiet loss when critically low on food
    if t % 400 == 0 and G['kodu'] < G['koduMax'] * 0.10 and G['ibu'] > 5 and random.random() < 0.3:
        G['ibu'] = max(2, G['ibu'] - 1)
        G['koduRate'] = max(0.1, G['koduRate'] - 0.04)
        M['negativeEvents']['ibuDrift'] += 1

    # Traveller auto-arrive
    travel_interval = 60 if G['nimaId'] == 'hash' else 120
    if G['sila'] >= 5 and t - G['lastTravelerTick'] > travel_interval:
        G['lastTravelerTick'] = t
        G['travelersHosted'] += 1
        G['munu'] = min(G['munu'] + munu_mult(G) * 1, G['munuMax'])

    # Auto-host — earned once a feno (barter agreement) exists: institutionalized
    # trust means hospitality no longer needs a person to personally extend it
    # each time. Fires the same effects as a manual host() click, on a timer,
    # so the player is freed from re-clicking it while still having farm/sibi/
    # trico/tega/sumi/bandits to actually make decisions about.
    if G['feno'] >= 1:
        auto_host_interval = 20  # ticks (~2s)
        if t - G['lastAutoHostTick'] >= auto_host_interval and G['kodu'] >= 10:
            G['lastAutoHostTick'] = t
            G['kodu'] -= 10
            G['sila'] = min(G['sila'] + sila_mult(G) * 2, G['silaMax'])
            G['munu'] = min(G['munu'] + munu_mult(G) * 3, G['munuMax'])
            G['travelersHosted'] += 1
            M['autoHostFires'] += 1

    # Bandit-bolo spawn — independent per-tick check (phase>=2, 400-tick cooldown,
    # 0.08%/tick chance), NOT part of the periodic-event roll below. Frontier
    # cells (adjacent to yours/allied/trico/free) are preferred, matching the
    # real game's spatial logic, though this doesn't affect economy/balance.
    if G['phase'] >= 2 and t - G['lastBanditTick'] > 400 and random.random() < 0.0008:
        G['lastBanditTick'] = t
        network = {'yours', 'allied', 'trico', 'free'}
        b_machine, b_frontier = [], []
        for i in range(1, 64):
            if G['map'][i] != 'machine':
                continue
            b_machine.append(i)
            r, c = i // 8, i % 8
            adj = []
            if r > 0: adj.append(i - 8)
            if r < 7: adj.append(i + 8)
            if c > 0: adj.append(i - 1)
            if c < 7: adj.append(i + 1)
            if any(G['map'][a] in network for a in adj):
                b_frontier.append(i)
        candidates = b_frontier if b_frontier else b_machine
        if candidates:
            bi = random.choice(candidates)
            G['map'][bi] = 'bandit'
            G['bandits'].append(bi)
            M['negativeEvents']['banditSpawn'] += 1

    # Bandit kodu drain
    if G['bandits'] and t % 20 == 0:
        G['kodu'] = max(0, G['kodu'] - len(G['bandits']) * 0.3)

    # Machine counter-offensive (below 30% grip)
    if not G['asaDone'] and 0 < G['machineGrip'] < 30 and t % 150 == 0:
        reclaimed = 0
        for i in range(64):
            if reclaimed >= 2: break
            if G['map'][i] in ('free', 'allied') and random.random() < 0.15:
                G['map'][i] = 'machine'
                G['machineGrip'] = min(35, G['machineGrip'] + 2)
                reclaimed += 1

    # Periodic events — one slot per 800 ticks minimum, phase>=2 only.
    # ibuSplit is always in the pool (its handler self-guards); sumiSecession
    # is conditionally added, matching triggerRandomEvent() exactly.
    if G['phase'] >= 2 and t - G['lastEventTick'] > 800 and t > 400:
        threshold = 0.007 if G['phase'] >= 3 else 0.012
        if random.random() < threshold:
            G['lastEventTick'] = t
            trigger_event(G)

    # Harvest penalty countdown
    if G['harvestPenalty'] > 0:
        G['harvestPenalty'] -= 1

    # Sumi secession drain (tightened: -3 every 4s, was -2 every 7s)
    if G['sumiSeceding'] and t % 40 == 0:
        if G['munu'] >= 3:
            G['munu'] -= 3
        else:
            G['sumiSeceding'] = False
            G['sumiCount'] = max(0, G['sumiCount'] - 1)
            G['machineGrip'] = min(95, G['machineGrip'] + 10)
            reverted = 0
            for i in range(64):
                if reverted >= 8: break
                if G['map'][i] == 'free' and random.random() < 0.4:
                    G['map'][i] = 'machine'
                    reverted += 1
            M['negativeEvents']['sumiLost'] += 1

    # Staged reveals (machine/exchange), tutStage 5 -> 6
    if G['tutStage'] == 5 and G['machineRevealAt'] and t >= G['machineRevealAt']:
        G['machineRevealAt'] = None
    if G['tutStage'] == 5 and G['exchangeRevealAt'] and t >= G['exchangeRevealAt']:
        G['exchangeRevealAt'] = None
        G['tutStage'] = 6
        mark_milestone(G, 'stage6_exchangeRevealed')

    if G['ibu'] > M['peakIbu']:
        M['peakIbu'] = G['ibu']

def trigger_event(G):
    t = G['tick']
    M = G['metrics']
    events = ['harvest', 'travelerTrouble', 'ibuSplit']
    if G['phase'] >= 3 and G['sumiCount'] >= 2 and not G['sumiSeceding']:
        events.append('sumiSecession')
    ev = random.choice(events)

    if ev == 'harvest':
        if G['harvestPenalty'] > 0:
            return  # already active, real handler no-ops too
        G['harvestPenalty'] = 400
        M['negativeEvents']['harvest'] += 1

    elif ev == 'travelerTrouble':
        cost = min(int(G['kodu'] * 0.08 + 5), int(G['kodu']))
        G['kodu'] = max(0, G['kodu'] - cost)
        G['sila'] = max(0, G['sila'] - 4)
        M['negativeEvents']['travelerTrouble'] += 1

    elif ev == 'ibuSplit':
        if G['ibu'] <= 14 or G['phase'] < 2:
            return  # real handler no-ops silently too
        lost = 2 if G['ibu'] > 20 else 1
        G['ibu'] = max(3, G['ibu'] - lost)
        G['koduRate'] = max(0.1, G['koduRate'] - lost * 0.04)
        G['munu'] = max(0, G['munu'] - 3)
        M['negativeEvents']['ibuSplit'] += 1

    elif ev == 'sumiSecession':
        G['sumiSeceding'] = True
        M['negativeEvents']['sumiSecession'] += 1

# ── AI STRATEGY ──────────────────────────────────────────────────────────────
# Priority order for actions, phase-aware. Returns action name or None.
#
# `prefs`, if given, is a per-run random weighting over {farm, sibi, host,
# munu} used to probabilistically choose among *currently affordable*
# identity-forming actions during tutStage 1-3 (before nima assignment).
# This replaced an earlier attempt at hand-written "styles" (farmer,
# host_lover, etc.) that biased the fixed priority order directly — those
# kept hitting brittle edge cases (e.g. an aggressive munu style spending
# sibi down to 2, then being unable to afford rebuilding it, and getting
# stuck only able to afford 'host' regardless of its intended bias).
# Randomized preferences sidestep that: they only ever choose among options
# that are actually affordable right now, so they can't strand the economy
# the way a rigid "always prefer X" rule can.

def weighted_identity_action(G, prefs, costs_sibi):
    available = identity_options_available(G)
    options = [(name, prefs[name]) for name in available]
    if not options:
        return None
    total = sum(w for _, w in options)
    r = random.random() * total
    acc = 0.0
    for name, w in options:
        acc += w
        if r <= acc:
            return name
    return options[-1][0]

def ai_action(G, prefs=None):
    phase = G['phase']
    tut = G['tutStage']

    if tut == 0:
        return 'farm' if G['kodu'] >= 5 else None

    # Deal with bandits first: absorb when kodu is healthy (grows population),
    # else yaka (cheaper, just needs munu).
    if G['bandits']:
        if G['kodu'] >= 25 and G['kodu'] >= G['koduMax'] * 0.3:
            return 'absorb'
        if G['munu'] >= 10:
            return 'yaka'

    # Phase 3+: push the organizing chain hard once material for it exists
    if phase >= 3:
        if G['tricoCount'] >= 5 and G['tegaCount'] < 9:
            return 'tega'
        if G['tegaCount'] >= 3 and G['sumiCount'] < 3:
            return 'sumi'
        if G['sumiBuilt'] >= 3 and not G['asaDone']:
            return 'asa'

    # Phase 2+: keep feeding the trico/feno chain when munu allows
    if phase >= 2 and tut >= 6 and G['munu'] >= 30:
        return 'trico'
    if phase >= 2 and G['munu'] >= 25 and G['feno'] < 5:
        return 'feno'

    costs_sibi = tut >= 3

    if prefs is not None and 1 <= tut <= 3:
        a = weighted_identity_action(G, prefs, costs_sibi)
        if a:
            return a
        # Falls through to the fixed core loop below only when nothing
        # preference-weighted is currently affordable (e.g. mid-farm-cycle).

    # Core loop (also the whole of the default/no-prefs "balanced" AI): keep
    # kodu healthy, staged farm currency respected.
    if costs_sibi:
        if G['sibi'] >= farm_cost(G) and G['kodu'] < G['koduMax'] * 0.6:
            return 'farm'
        if G['kodu'] >= sibi_cost(G) and G['sibi'] < 15:
            return 'sibi'
    else:
        if G['kodu'] >= farm_cost(G) and G['kodu'] < G['koduMax'] * 0.6:
            return 'farm'
        if G['kodu'] >= sibi_cost(G) and G['sibi'] < 15:
            return 'sibi'

    if G['kodu'] >= ibu_cost(G) + 20 and G['ibu'] < 20:
        return 'ibu'
    # Manual host is only needed before auto-host is earned (via feno); after
    # that, hospitality takes care of itself and this branch stays dormant.
    if tut >= 2 and G['feno'] == 0 and G['kodu'] >= 15 and G['sila'] < G['silaMax'] * 0.7:
        return 'host'
    if tut >= 3 and G['sibi'] >= 10 and G['munu'] < 40:
        return 'munu'

    # Fallback
    if not costs_sibi and G['kodu'] >= farm_cost(G):
        return 'farm'
    if costs_sibi and G['sibi'] >= farm_cost(G):
        return 'farm'
    if tut >= 2 and G['feno'] == 0 and G['kodu'] >= 10:
        return 'host'

    return None

def random_prefs():
    keys = ['farm', 'sibi', 'host', 'munu']
    return {k: random.uniform(0.2, 2.0) for k in keys}

# ── VISITORS — narrative relationship layer (PROTOTYPE, not yet in the game) ─
# Named neighbour-bolos that recur across a playthrough instead of the
# anonymous "traveller" pop-in. Each visit is one discrete choice — welcome /
# trade / turn away — with a resource cost and a trust delta that PERSISTS
# per visitor. Trust gates two threads:
#   trust >= ALLY_THRESHOLD    -> becomes an ally: small passive gift trickle
#                                  for the rest of the game.
#   trust <= HOSTILE_THRESHOLD -> becomes a "grudge": drains kodu every tick
#                                  (same magnitude as one bandit) until the
#                                  player resolves it with the game's EXISTING
#                                  verbs — absorb (reconcile, costs kodu,
#                                  trust resets and they can be seen again) or
#                                  yaka (expel, costs munu, permanently lost).
# Deliberately reuses absorb/yaka rather than inventing new verbs, so "a
# neighbour you snubbed turns hostile" plays exactly like the bandit-bolo
# mechanic the player already understands — narrative reframing of existing
# numbers, not new systems.
#
# Wired up via run_once_social() only — new_game/tick/do_action are untouched
# so every previously-validated baseline run above still behaves identically.

# ── VISITOR PACKS — versioned so an old config stays runnable for direct
# comparison rather than being overwritten. Add new packs as 'v3', 'v4', etc;
# never mutate a shipped pack's content in place. run_once_social(pack='v2')
# selects which one drives a given batch of runs.
#
# VERSION LOG
#   v1 — first prototype. 3 independent personalities, flavour grounded in
#        real bolo'bolo glossary terms (yalu/gano/taku) but NOT tied to the
#        game's own nima system. Single repeat-visit line each (later found
#        repetitive in long traces). No mechanical link to player identity.
#   v2 — ties each visitor to one of the game's existing nima archetypes
#        (hash/craft/eco — chosen because their built-in flavour already
#        reads as hospitality/craft/conservation-minded, so no rewrite of
#        the core v1 lines was needed, just reframing + extension). Adds:
#          - 3 rotating repeat-visit lines per visitor (kills the copy-paste
#            feel of a single repeated line across a playthrough)
#          - an affinity mechanic: once the player's own nima is assigned,
#            a visitor sharing that nima gains trust faster from the player
#            (kindred bolos recognise their own) and is more forgiving of a
#            turnAway — the actual replayability lever, since which visitor
#            that is depends on how THIS run's nima was earned.
VISITOR_PACKS = {}

VISITOR_PACKS['v1'] = {
    'label': 'v1 (independent personalities, no nima tie-in)',
    'ally_threshold': 30,
    'hostile_threshold': -30,
    'visit_cooldown': 150,  # ticks (~15s) between any two visits
    'affinity_multiplier': None,  # no affinity mechanic in v1
    'visitors': [
        {'name': 'Ridge-bolo', 'nima': None},
        {'name': 'Marsh-bolo', 'nima': None},
        {'name': 'Grove-bolo', 'nima': None},
    ],
    'flavor': {
        'Ridge-bolo': {
            'first':    "Ridge-bolo sends word ahead: they are between harvests, and their yalu are hungry.",
            'repeat':   ["A knot of Ridge-bolo travellers appears at the frontier again."],
            'welcome':  "You lay out kodu and sibi without asking why. Ridge-bolo takes note: this is a bolo that keeps sila.",
            'trade':    "Goods change hands, measured and fair. Ridge-bolo nods — correct, if not warm.",
            'turnAway': "You have nothing to spare today. Ridge-bolo's yalu turn back toward the ridge, saying little.",
            'ally':     "Ridge-bolo now sends kodu unasked, the way sila was meant to work.",
            'hostile':  "Ridge-bolo stops sending word. What comes from the ridge now takes without asking.",
            'reconcile':"You open your stores to Ridge-bolo without conditions. The grudge doesn't survive contact with sila.",
            'expel':    "A yaka is issued. Ridge-bolo's exchange with your bolo ends — for good, this time.",
        },
        'Marsh-bolo': {
            'first':    "Marsh-bolo's gano sends a delegation, sibi in hand, looking to trade rather than beg.",
            'repeat':   ["Marsh-bolo's traders are back, sibi bundled and ready."],
            'welcome':  "You host them properly — food, rest, no ledger kept. Marsh-bolo isn't used to being treated as more than a trading partner.",
            'trade':    "Sibi for sibi, straightforward. Marsh-bolo respects a fair exchange.",
            'turnAway': "You wave them off before the goods are even unpacked. Marsh-bolo repacks without a word.",
            'ally':     "Marsh-bolo starts sending finished goods before you ask for them.",
            'hostile':  "Marsh-bolo's gano stops offering fair trades. What they send now, they send to take.",
            'reconcile':"You give without expecting sibi in return. Marsh-bolo lowers its guard.",
            'expel':    "A yaka is issued. Marsh-bolo's workshops close their gates to your bolo.",
        },
        'Grove-bolo': {
            'first':    "Grove-bolo sends a small party — they keep close counts of everything, taku-fashion, and watch how you count too.",
            'repeat':   ["Grove-bolo's counters return, still watching."],
            'welcome':  "You give more than the taku would strictly allow. Grove-bolo studies you for a long moment before accepting.",
            'trade':    "An exact trade, nothing over. Grove-bolo approves of the precision.",
            'turnAway': "You send them away empty-handed. Grove-bolo records it — they always record it.",
            'ally':     "Grove-bolo's caution finally breaks. They begin sharing surplus they'd normally hoard.",
            'hostile':  "Grove-bolo's counters stop coming. Their taku now excludes your bolo entirely.",
            'reconcile':"Patient, exact generosity — the only kind Grove-bolo trusts — wins them back.",
            'expel':    "A yaka is issued. Grove-bolo strikes your bolo from its taku for good.",
        },
    },
}

VISITOR_PACKS['v2'] = {
    'label': 'v2 (nima-tagged: Ridge=hash, Marsh=craft, Grove=eco; rotating repeats; kindred affinity)',
    'ally_threshold': 30,
    'hostile_threshold': -30,
    'visit_cooldown': 150,
    'affinity_multiplier': 1.5,  # kindred-nima trust gain multiplier (see resolve_visit)
    'visitors': [
        {'name': 'Ridge-bolo', 'nima': 'hash'},
        {'name': 'Marsh-bolo', 'nima': 'craft'},
        {'name': 'Grove-bolo', 'nima': 'eco'},
    ],
    'flavor': {
        'Ridge-bolo': {
            'first':    "Ridge-bolo sends word ahead: they are between harvests, and their yalu are hungry.",
            'repeat':   ["A knot of Ridge-bolo travellers appears at the frontier again.",
                         "More of Ridge-bolo's yalu drift in, the same unhurried way as before.",
                         "Ridge-bolo sends another party — no message this time, just people."],
            'welcome':  "You lay out kodu and sibi without asking why. Ridge-bolo takes note: this is a bolo that keeps sila.",
            'trade':    "Goods change hands, measured and fair. Ridge-bolo nods — correct, if not warm.",
            'turnAway': "You have nothing to spare today. Ridge-bolo's yalu turn back toward the ridge, saying little.",
            'ally':     "Ridge-bolo now sends kodu unasked, the way sila was meant to work.",
            'hostile':  "Ridge-bolo stops sending word. What comes from the ridge now takes without asking.",
            'reconcile':"You open your stores to Ridge-bolo without conditions. The grudge doesn't survive contact with sila.",
            'expel':    "A yaka is issued. Ridge-bolo's exchange with your bolo ends — for good, this time.",
            'kindred':  "Ridge-bolo's yalu recognise something familiar in how easily your bolo takes people in.",
        },
        'Marsh-bolo': {
            'first':    "Marsh-bolo's gano sends a delegation, sibi in hand, looking to trade rather than beg.",
            'repeat':   ["Marsh-bolo's traders are back, sibi bundled and ready.",
                         "Marsh-bolo's gano sends another shipment out to test the market.",
                         "A Marsh-bolo cart arrives, wheels creaking under new stock."],
            'welcome':  "You host them properly — food, rest, no ledger kept. Marsh-bolo isn't used to being treated as more than a trading partner.",
            'trade':    "Sibi for sibi, straightforward. Marsh-bolo respects a fair exchange.",
            'turnAway': "You wave them off before the goods are even unpacked. Marsh-bolo repacks without a word.",
            'ally':     "Marsh-bolo starts sending finished goods before you ask for them.",
            'hostile':  "Marsh-bolo's gano stops offering fair trades. What they send now, they send to take.",
            'reconcile':"You give without expecting sibi in return. Marsh-bolo lowers its guard.",
            'expel':    "A yaka is issued. Marsh-bolo's workshops close their gates to your bolo.",
            'kindred':  "Marsh-bolo's gano recognises a fellow craft-minded bolo — the trade goes easier from here.",
        },
        'Grove-bolo': {
            'first':    "Grove-bolo sends a small party — they keep close counts of everything, taku-fashion, and watch how you count too.",
            'repeat':   ["Grove-bolo's counters return, still watching.",
                         "Grove-bolo sends its tally-keepers again, taku ledgers in hand.",
                         "Another careful delegation from Grove-bolo, counting as they walk."],
            'welcome':  "You give more than the taku would strictly allow. Grove-bolo studies you for a long moment before accepting.",
            'trade':    "An exact trade, nothing over. Grove-bolo approves of the precision.",
            'turnAway': "You send them away empty-handed. Grove-bolo records it — they always record it.",
            'ally':     "Grove-bolo's caution finally breaks. They begin sharing surplus they'd normally hoard.",
            'hostile':  "Grove-bolo's counters stop coming. Their taku now excludes your bolo entirely.",
            'reconcile':"Patient, exact generosity — the only kind Grove-bolo trusts — wins them back.",
            'expel':    "A yaka is issued. Grove-bolo strikes your bolo from its taku for good.",
            'kindred':  "Grove-bolo recognises its own caution mirrored back — the counting relaxes, just slightly.",
        },
    },
}
# Tuning history (applies to both packs — shared mechanic constants):
# started with 5 visitors / ±60 thresholds / 300-tick cooldown, matching old
# anonymous-traveller cadence — that produced ZERO allies and ZERO hostiles
# across 75 test runs (15 x 5 strategy combos). Typical win time is 400-750s,
# so 5 names sharing a 30s cooldown means each visitor is only seen 2-3 times
# per playthrough — never enough reps to cross a ±40/60 threshold. Cut to 3
# names, halved the cooldown, and roughly doubled trust deltas (see
# resolve_visit) so a consistent playstyle can actually resolve an arc
# (ally or grudge) within one game.

def new_visitors(pack):
    return [{'name': v['name'], 'nima': v['nima'], 'trust': 0, 'visits': 0,
             'met': False, 'ally': False, 'hostile': False, 'lost': False,
             'kindredShown': False}
            for v in pack['visitors']]

def pick_visit_target(G):
    pool = [v for v in G['visitors'] if not v['hostile'] and not v['lost']]
    if not pool:
        return None
    unmet = [v for v in pool if not v['met']]
    if unmet:
        return unmet[0]  # first-time intros before repeat visits
    return min(pool, key=lambda v: v['visits'])  # spread visits round-robin

def visit_choice(G, strategy, v):
    """Which response a given 'social strategy' picks, among what's
    affordable right now. Mirrors weighted_identity_action's pattern of only
    choosing among currently-viable options."""
    can_welcome = G['kodu'] >= 10 and G['sibi'] >= 4
    can_trade = G['sibi'] >= 6
    if strategy == 'generous':
        if can_welcome: return 'welcome'
        if can_trade: return 'trade'
        return 'turnAway'
    if strategy == 'guarded':
        if v['trust'] < 0 and can_welcome: return 'welcome'  # repair only when already sour
        if can_trade: return 'trade'
        return 'turnAway'
    if strategy == 'random':
        opts = ['turnAway']
        if can_welcome: opts.append('welcome')
        if can_trade: opts.append('trade')
        return random.choice(opts)
    return 'turnAway'  # 'neglect' / unrecognised strategy

def resolve_visit(G, v, choice, M, pack):
    flavor = pack['flavor'].get(v['name'], {})
    if not v['met']:
        intro = flavor.get('first')
    else:
        repeats = flavor.get('repeat') or []
        intro = repeats[v['visits'] % len(repeats)] if repeats else None
    if intro:
        M['visitorMilestones'].append((G['tick'], intro))
    v['met'] = True
    v['visits'] += 1

    # Kindred-nima affinity (v2+): once the player's own nima is assigned, a
    # visitor sharing that nima gains trust faster and forgives a turnAway
    # more easily — "kindred bolos recognise their own." This is the actual
    # replayability lever: which visitor gets the boost depends on how this
    # particular run's nima was earned.
    affinity = pack.get('affinity_multiplier')
    kindred = bool(affinity and G.get('nimaId') and v['nima'] == G['nimaId'])
    if kindred and not v['kindredShown']:
        v['kindredShown'] = True
        if flavor.get('kindred'):
            M['visitorMilestones'].append((G['tick'], flavor['kindred']))

    if choice == 'welcome':
        G['kodu'] -= 10
        G['sibi'] -= 4
        delta = 20 * affinity if kindred else 20
        v['trust'] = min(100, v['trust'] + delta)
        G['munu'] = min(G['munu'] + munu_mult(G) * 4, G['munuMax'])
        G['sila'] = min(G['sila'] + 2, G['silaMax'])
    elif choice == 'trade':
        G['sibi'] -= 6
        delta = 8 * affinity if kindred else 8
        v['trust'] = min(100, v['trust'] + delta)
        G['munu'] = min(G['munu'] + munu_mult(G) * 2, G['munuMax'])
    else:  # turnAway
        delta = 6 * 0.5 if kindred else 6  # kindred bolos are more forgiving
        v['trust'] = max(-100, v['trust'] - delta)
    if choice in flavor:
        M['visitorMilestones'].append((G['tick'], flavor[choice]))

    if v['trust'] >= pack['ally_threshold'] and not v['ally']:
        v['ally'] = True
        M['visitorMilestones'].append((G['tick'], flavor.get('ally', f"ALLY: {v['name']}")))
    if v['trust'] <= pack['hostile_threshold'] and not v['hostile']:
        v['hostile'] = True
        M['visitorMilestones'].append((G['tick'], flavor.get('hostile', f"HOSTILE: {v['name']}")))

def process_visitors(G, social_strategy, M, pack):
    if G['tick'] - G['lastVisitTick'] < pack['visit_cooldown']:
        return
    if G['sila'] < 5:
        return
    v = pick_visit_target(G)
    if v is None:
        return
    G['lastVisitTick'] = G['tick']
    choice = visit_choice(G, social_strategy, v)
    resolve_visit(G, v, choice, M, pack)

def process_grudges(G, conflict_strategy, M, pack):
    hostiles = [v for v in G['visitors'] if v['hostile']]
    if not hostiles:
        return
    if G['tick'] % 20 == 0:
        G['kodu'] = max(0, G['kodu'] - len(hostiles) * 0.3)  # same drain as one bandit
    if conflict_strategy == 'neglect':
        return
    target = hostiles[0]
    flavor = pack['flavor'].get(target['name'], {})
    if conflict_strategy == 'diplomatic' and G['kodu'] >= 25:
        G['kodu'] -= 25
        target['hostile'] = False
        target['trust'] = 10
        M['reconciled'] += 1
        M['visitorMilestones'].append((G['tick'], flavor.get('reconcile', f"RECONCILED: {target['name']}")))
    elif conflict_strategy == 'aggressive' and G['munu'] >= 10:
        G['munu'] -= 10
        target['hostile'] = False
        target['lost'] = True
        M['expelled'] += 1
        M['visitorMilestones'].append((G['tick'], flavor.get('expel', f"EXPELLED: {target['name']}")))

def ally_gifts(G):
    allies = [v for v in G['visitors'] if v['ally']]
    if allies and G['tick'] % 10 == 0:
        G['kodu'] = min(G['kodu'] + len(allies) * 0.15, G['koduMax'])

# ── SINGLE RUN ───────────────────────────────────────────────────────────────

def run_once(chosen_nima=None, prefs=None, verbose=False, seed=None):
    if seed is not None:
        random.seed(seed)
    G = new_game(chosen_nima)
    last_action_tick = -5
    action_cooldown = 3  # matches a human clicking roughly every 300ms at most

    def row(label=""):
        print(f"{G['tick']:>6} {G['tick']/TICK_RATE:>6.0f}s tut={G['tutStage']:>1} ph={G['phase']} "
              f"ibu={G['ibu']:>4.0f} kodu={G['kodu']:>6.1f} sibi={G['sibi']:>5.1f} munu={G['munu']:>5.1f} "
              f"grip={G['machineGrip']:>5.1f} | {label}")

    for _ in range(MAX_TICKS):
        tick(G)
        t = G['tick']

        while G['events']:
            evtick, label = G['events'].pop(0)
            if verbose: row(label)

        if t - last_action_tick >= action_cooldown:
            action = ai_action(G, prefs)
            if action is None:
                G['metrics']['idleTicks'] += 1
            elif do_action(G, action):
                last_action_tick = t
                G['metrics']['totalActions'] += 1
                G['metrics']['actionCounts'][action] = G['metrics']['actionCounts'].get(action, 0) + 1

        if verbose and t % DEBUG_INTERVAL == 0:
            row(f"--- nima={G['nimaId']} farmLv={G['farmLv']} sibiLv={G['sibiLv']} "
                f"trico={G['tricoCount']} tega={G['tegaCount']} sumi={G['sumiCount']} "
                f"bandits={len(G['bandits'])}")

        if G['asaDone']:
            if verbose:
                row("*** ASA'DALA — THE MACHINE IS GONE ***")
            return G

    return G  # timed out

def run_once_social(chosen_nima=None, prefs=None, social_strategy='generous',
                     conflict_strategy='diplomatic', pack='v2', verbose=False, seed=None):
    """Same as run_once, plus the visitor relationship layer. Kept as a
    separate function (rather than a flag on run_once) so the baseline sim
    above is provably untouched. `pack` selects a VISITOR_PACKS entry —
    defaults to the latest ('v2'); pass 'v1' to reproduce the earlier
    prototype for direct comparison."""
    if seed is not None:
        random.seed(seed)
    P = VISITOR_PACKS[pack]
    G = new_game(chosen_nima)
    G['visitors'] = new_visitors(P)
    G['lastVisitTick'] = 0
    last_action_tick = -5
    action_cooldown = 3

    def row(label=""):
        print(f"{G['tick']:>6} {G['tick']/TICK_RATE:>6.0f}s tut={G['tutStage']:>1} ph={G['phase']} "
              f"ibu={G['ibu']:>4.0f} kodu={G['kodu']:>6.1f} sibi={G['sibi']:>5.1f} munu={G['munu']:>5.1f} "
              f"grip={G['machineGrip']:>5.1f} | {label}")

    for _ in range(MAX_TICKS):
        tick(G)
        process_visitors(G, social_strategy, G['metrics'], P)
        process_grudges(G, conflict_strategy, G['metrics'], P)
        ally_gifts(G)
        t = G['tick']

        while G['events']:
            evtick, label = G['events'].pop(0)
            if verbose: row(label)
        while G['metrics']['visitorMilestones']:
            evtick, label = G['metrics']['visitorMilestones'].pop(0)
            if verbose: row(label)

        if t - last_action_tick >= action_cooldown:
            action = ai_action(G, prefs)
            if action is None:
                G['metrics']['idleTicks'] += 1
            elif do_action(G, action):
                last_action_tick = t
                G['metrics']['totalActions'] += 1
                G['metrics']['actionCounts'][action] = G['metrics']['actionCounts'].get(action, 0) + 1

        if verbose and t % DEBUG_INTERVAL == 0:
            row(f"--- nima={G['nimaId']} farmLv={G['farmLv']} sibiLv={G['sibiLv']} "
                f"trico={G['tricoCount']} tega={G['tegaCount']} sumi={G['sumiCount']} "
                f"bandits={len(G['bandits'])} grudges={sum(1 for v in G['visitors'] if v['hostile'])}")

        if G['asaDone']:
            if verbose:
                row("*** ASA'DALA — THE MACHINE IS GONE ***")
            return G

    return G  # timed out

def summarize_social(runs, label):
    print("\n" + "=" * 78)
    print(f"SOCIAL LAYER SUMMARY: {label} ({len(runs)} runs)")
    print("=" * 78)
    wins = [g for g in runs if g['asaDone']]
    print(f"Wins: {len(wins)}/{len(runs)}", end="")
    if wins:
        times = [g['tick'] / TICK_RATE for g in wins]
        print(f"   win time median={statistics.median(times):.0f}s max={max(times):.0f}s")
    else:
        print()

    allies = [sum(1 for v in g['visitors'] if v['ally']) for g in runs]
    hostile_ever = [sum(1 for v in g['visitors'] if v['hostile'] or v['lost']) for g in runs]
    lost = [sum(1 for v in g['visitors'] if v['lost']) for g in runs]
    reconciled = [g['metrics']['reconciled'] for g in runs]
    kodu_zero = [g['metrics']['koduZeroTicks'] for g in runs]
    roster_size = len(runs[0]['visitors'])
    print(f"Allies at end:        median={statistics.median(allies):.1f}  max={max(allies)}  (of {roster_size})")
    print(f"Ever hostile/lost:    median={statistics.median(hostile_ever):.1f}  max={max(hostile_ever)}")
    print(f"Permanently lost:     median={statistics.median(lost):.1f}  max={max(lost)}")
    print(f"Reconciled count:     median={statistics.median(reconciled):.1f}")
    print(f"Ticks at 0 kodu:      median={statistics.median(kodu_zero):.0f}  max={max(kodu_zero)}  (soft-lock proxy)")

# ── MULTI-RUN ANALYSIS ───────────────────────────────────────────────────────

MILESTONE_ORDER = [
    'stage1_sibiRevealed', 'stage2_hospitalityRevealed', 'stage3_munuRevealed',
    'stage4_nimaAssigned', 'stage6_exchangeRevealed', 'firstTrico', 'firstFeno',
    'phase3', 'firstTega', 'firstSumi', 'win',
]

def summarize(runs):
    print("\n" + "=" * 78)
    print(f"SUMMARY over {len(runs)} runs")
    print("=" * 78)

    wins = [g for g in runs if g['asaDone']]
    print(f"Wins: {len(wins)}/{len(runs)}")
    if wins:
        times = [g['tick'] / TICK_RATE for g in wins]
        print(f"Win time (s):  min={min(times):.0f}  max={max(times):.0f}  "
              f"mean={statistics.mean(times):.0f}  median={statistics.median(times):.0f}"
              + (f"  stdev={statistics.stdev(times):.0f}" if len(times) > 1 else ""))

    print("\n--- Median tick each milestone is first reached (real seconds) ---")
    for name in MILESTONE_ORDER:
        vals = [g['metrics']['milestones'][name] for g in runs if name in g['metrics']['milestones']]
        if vals:
            med = statistics.median(vals) / TICK_RATE
            hit_rate = len(vals) / len(runs) * 100
            print(f"  {name:28s} {med:7.0f}s   (reached in {hit_rate:.0f}% of runs)")
        else:
            print(f"  {name:28s}  never reached")

    print("\n--- Negative events (median count per run) ---")
    all_keys = runs[0]['metrics']['negativeEvents'].keys()
    for k in all_keys:
        vals = [g['metrics']['negativeEvents'][k] for g in runs]
        print(f"  {k:20s} median={statistics.median(vals):.1f}  max={max(vals)}")

    print("\n--- Action mix (median count per run) ---")
    all_actions = set()
    for g in runs:
        all_actions.update(g['metrics']['actionCounts'].keys())
    for a in sorted(all_actions):
        vals = [g['metrics']['actionCounts'].get(a, 0) for g in runs]
        print(f"  {a:10s} median={statistics.median(vals):.0f}  max={max(vals)}")

    total_actions = [g['metrics']['totalActions'] for g in runs]
    manual_hosts = [g['metrics']['actionCounts'].get('host', 0) for g in runs]
    auto_hosts = [g['metrics']['autoHostFires'] for g in runs]
    idle = [g['metrics']['idleTicks'] for g in runs]
    kodu_zero = [g['metrics']['koduZeroTicks'] for g in runs]
    peak_ibu = [g['metrics']['peakIbu'] for g in runs]
    print(f"\nTotal MANUAL actions taken:  median={statistics.median(total_actions):.0f}")
    print(f"  of which 'host' clicks:    median={statistics.median(manual_hosts):.0f}")
    print(f"Auto-host firings (not clicks): median={statistics.median(auto_hosts):.0f}  max={max(auto_hosts)}")
    print(f"Idle ticks (no valid action, AI checked every {3/TICK_RATE*1000:.0f}ms): "
          f"median={statistics.median(idle):.0f}")
    print(f"Ticks spent at 0 kodu (frustration proxy): median={statistics.median(kodu_zero):.0f}  "
          f"max={max(kodu_zero)}")
    print(f"Peak population (ibu) reached: median={statistics.median(peak_ibu):.0f}  "
          f"min={min(peak_ibu):.0f}  max={max(peak_ibu):.0f}")

    nima_counts = {}
    for g in runs:
        nima_counts[g['nimaId']] = nima_counts.get(g['nimaId'], 0) + 1
    print(f"\nNima distribution: {nima_counts}")


if __name__ == '__main__':
    N = 8
    N_VARIED = 60

    print(f"=== bolo'bolo SIMULATION — {N} runs, undecided nima, fixed 'balanced' AI ===")
    balanced_runs = [run_once(chosen_nima=None, seed=i) for i in range(N)]
    summarize(balanced_runs)

    print(f"\n\n=== {N} runs, nima chosen at start (agro), fixed 'balanced' AI ===")
    runs_agro = [run_once(chosen_nima='agro', seed=1000 + i) for i in range(N)]
    summarize(runs_agro)

    print(f"\n\n=== {N_VARIED} runs, undecided nima, RANDOMIZED per-run preferences ===")
    print("Each run samples its own random weighting over {farm, sibi, host, munu}")
    print("and probabilistically picks among whatever's affordable — testing whether")
    print("genuine behavioural variation (not one fixed AI) produces varied nimas.\n")
    varied_runs = []
    for i in range(N_VARIED):
        random.seed(2000 + i)
        prefs = random_prefs()
        g = run_once(chosen_nima=None, prefs=prefs, seed=2000 + i)
        varied_runs.append(g)
        prefs_str = " ".join(f"{k}:{v:.1f}" for k, v in prefs.items())
        outcome = f"WIN {round(g['tick']/TICK_RATE)}s" if g['asaDone'] else "TIMEOUT"
        nima_str = g['nimaId'] or 'NONE'
        print(f"  run {i:2d}  prefs=[{prefs_str}]  -> nima={nima_str:10s} {outcome}")

    nima_counts = {}
    for g in varied_runs:
        nima_counts[g['nimaId']] = nima_counts.get(g['nimaId'], 0) + 1
    wins = sum(1 for g in varied_runs if g['asaDone'])
    print(f"\nNima distribution across {N_VARIED} randomized runs: {nima_counts}")
    print(f"Wins: {wins}/{N_VARIED}")
    if not all(g['asaDone'] for g in varied_runs):
        print("*** NOT ALL RUNS WON — see TIMEOUT rows above ***")

    print("\n\n=== One verbose run (undecided nima, balanced AI, seed=42) for a readable trace ===")
    run_once(chosen_nima=None, verbose=True, seed=42)

    # ── VISITOR / RELATIONSHIP LAYER PROTOTYPE ──────────────────────────────
    print("\n\n" + "#" * 78)
    print("# VISITOR LAYER — narrative relationship prototype")
    print("#" * 78)
    N_SOCIAL = 15
    scenarios = [
        ('generous',  'diplomatic'),
        ('guarded',   'diplomatic'),
        ('random',    'diplomatic'),
        ('guarded',   'aggressive'),
        ('random',    'neglect'),   # stress test: never resolves grudges
    ]

    for pack_id in ['v1', 'v2']:
        print(f"\n--- pack {pack_id}: {VISITOR_PACKS[pack_id]['label']} ---")
        for social, conflict in scenarios:
            runs = [run_once_social(social_strategy=social, conflict_strategy=conflict, pack=pack_id, seed=3000 + i)
                    for i in range(N_SOCIAL)]
            summarize_social(runs, f"[{pack_id}] social={social} conflict={conflict}")

    # v2-only: does the kindred-nima affinity mechanic actually change outcomes
    # depending on which nima the run ends up with? This is the concrete test
    # of the "will it help replayability" claim — same generous strategy,
    # only chosen_nima differs. Compared WITHIN each run (kindred visitor's
    # trust vs the average of the other two) rather than across runs, since
    # different nimas produce different game lengths on their own (eco/craft
    # games run longer than agro/anarcho ones — see the balance sim above),
    # which would otherwise confound a same-strategy ally-count comparison.
    print("\n\n" + "#" * 78)
    print("# v2 AFFINITY CHECK — same 'generous' strategy, different chosen_nima")
    print("#" * 78)
    for nima_choice in ['eco', 'craft', 'hash', 'agro']:  # agro has no matching visitor (control)
        runs = [run_once_social(chosen_nima=nima_choice, social_strategy='generous',
                                 conflict_strategy='diplomatic', pack='v2', seed=4000 + i)
                for i in range(N_SOCIAL)]
        kindred_trust, other_trust = [], []
        for g in runs:
            for v in g['visitors']:
                (kindred_trust if v['nima'] == nima_choice else other_trust).append(v['trust'])
        k_avg = statistics.mean(kindred_trust) if kindred_trust else None
        o_avg = statistics.mean(other_trust) if other_trust else None
        k_str = f"{k_avg:6.1f}" if k_avg is not None else "  n/a "
        print(f"  chosen_nima={nima_choice:6s}  kindred-visitor avg trust={k_str}   "
              f"other-two avg trust={o_avg:6.1f}   win-time median="
              f"{statistics.median(g['tick']/TICK_RATE for g in runs):.0f}s")

    print("\n\n=== One verbose social run, pack=v2, generous/diplomatic, seed=42 ===")
    run_once_social(social_strategy='generous', conflict_strategy='diplomatic', pack='v2', verbose=True, seed=42)
