import random
import math

random.seed(42)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TICK_RATE = 10  # ticks per second (each tick = 100ms)
MAX_TICKS = 50000  # ~83 minutes max
DEBUG_INTERVAL = 500  # print state every N ticks

# ── AI STRATEGY ──────────────────────────────────────────────────────────────
# Priority order for actions, phase-aware
# Returns action name or None

def ai_action(G):
    phase = G['phase']
    tut = G['tutStage']

    # Stage 0: farm once to unlock sibi
    if tut == 0:
        if G['kodu'] >= 5:
            return 'farm'
        return None

    # Always keep kodu healthy - farm if sibi available and kodu below 60% cap
    if G['sibi'] >= farm_cost(G) and G['kodu'] < G['koduMax'] * 0.6:
        return 'farm'

    # Build sibi if we have kodu and sibi is getting low
    if G['kodu'] >= sibi_cost(G) and G['sibi'] < 15:
        return 'sibi'

    # Welcome ibu if kodu is comfortable
    if G['kodu'] >= ibu_cost(G) + 20 and G['ibu'] < 20:
        return 'ibu'

    # Hospitality once unlocked
    if tut >= 2 and G['kodu'] >= 15 and G['sila'] < G['silaMax'] * 0.7:
        return 'host'

    # Spread munu once unlocked
    if tut >= 3 and G['sibi'] >= 10 and G['munu'] < 40:
        return 'munu'

    # Phase 2+: build trico when munu available
    if phase >= 2 and tut >= 6 and G['munu'] >= 30:
        return 'trico'

    # Phase 2+: build feno when munu available
    if phase >= 2 and G['munu'] >= 25 and G['feno'] < 5:
        return 'feno'

    # Phase 3: tega -> sumi -> asa
    if phase >= 3:
        if G['tricoCount'] >= 5 and G['tegaCount'] < 9:
            return 'tega'
        if G['tegaCount'] >= 3 and G['sumiCount'] < 3:
            return 'sumi'
        if G.get('sumiBuilt',0) >= 3 and not G['asaDone']:
            return 'asa'

    # Deal with bandits
    if G['bandits'] and G['munu'] >= 10:
        return 'yaka'

    # Default: farm if possible, else host to build munu
    if G['sibi'] >= farm_cost(G):
        return 'farm'
    if tut >= 2 and G['kodu'] >= 10:
        return 'host'

    return None

# ── COSTS ────────────────────────────────────────────────────────────────────

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

# ── NIMA ASSIGNMENT ──────────────────────────────────────────────────────────

NIMAS = {
    'agro':    {'bonus': 'koduRate x2'},
    'craft':   {'bonus': 'sibiRate +0.3'},
    'eco':     {'bonus': 'koduMax 400'},
    'anarcho': {'bonus': 'munu x2'},
    'franco':  {'bonus': 'silaMax 150'},
    'dada':    {'bonus': 'random'},
    'tao':     {'bonus': 'auto kodu'},
    'hash':    {'bonus': 'traveler bonus'},
}

def assign_nima(G):
    f, si, h, m = G['farmActions'], G['sibiActions'], G['hostActions'], G['munuActions']
    total = f + si + h + m
    if total == 0:
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

def new_game():
    G = {
        'tick': 0, 'phase': 1, 'tutStage': 0,
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
        'lastEventTick': 0,
        'lastTravelerTick': 0,
        'harvestPenalty': 0,
        'sumiSeceding': False,
        'nimaId': None,
        'farmActions': 0, 'sibiActions': 0, 'hostActions': 0, 'munuActions': 0,
        'machineRevealAt': None, 'exchangeRevealAt': None,
        'events': [],  # log of notable events
    }
    G['map'] = ['machine'] * 64
    G['map'][0] = 'yours'
    return G

# ── ACTION EXECUTION ─────────────────────────────────────────────────────────

def do_action(G, action):
    t = G['tick']
    tut = G['tutStage']

    if action == 'farm':
        if tut == 0:
            if G['kodu'] < 5: return False
            G['kodu'] -= 5
            G['koduRate'] += 0.2
            G['farmActions'] += 1
            check_tutorial(G)
            return True
        c = farm_cost(G)
        if G['sibi'] < c: return False
        G['sibi'] -= c
        G['farmLv'] += 1
        G['koduRate'] += 0.45 if G['nimaId'] == 'agro' else 0.22
        G['koduMax'] += 30
        G['farmActions'] += 1
        check_tutorial(G)
        return True

    elif action == 'sibi':
        c = sibi_cost(G)
        if G['kodu'] < c: return False
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
        check_tutorial(G)
        return True

    elif action == 'host':
        if G['kodu'] < 10: return False
        G['kodu'] -= 10
        G['sila'] = min(G['sila'] + sila_mult(G) * 2, G['silaMax'])
        G['munu'] = min(G['munu'] + munu_mult(G) * 3, G['munuMax'])
        G['travelersHosted'] += 1
        G['hostActions'] += 1
        check_tutorial(G)
        check_phase(G)
        return True

    elif action == 'munu':
        if G['sibi'] < 5: return False
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
        # Add trico cells to map
        for i in range(len(G['map'])):
            if G['map'][i] == 'machine' and random.random() < 0.05:
                G['map'][i] = 'trico'
                break
        G['machineGrip'] = max(0, G['machineGrip'] - 3)
        check_phase(G)
        return True

    elif action == 'feno':
        if G['munu'] < 20: return False
        G['munu'] -= 20
        G['feno'] += 1
        G['koduRate'] += 0.1
        G['sibiRate'] += 0.04
        return True

    elif action == 'tega':
        if G['tricoCount'] < 5: return False
        G['tegaCount'] += 1
        G['tricoCount'] -= 5  # consume 5 trico
        G['machineGrip'] = max(0, G['machineGrip'] - 15)
        # Flip some cells
        for i in range(len(G['map'])):
            if G['map'][i] == 'machine' and random.random() < 0.1:
                G['map'][i] = 'allied'
        check_phase(G)
        return True

    elif action == 'sumi':
        if G['tegaCount'] < 3: return False
        G["sumiCount"] += 1
        G["sumiBuilt"] = G.get("sumiBuilt", 0) + 1
        G['tegaCount'] -= 3
        G['machineGrip'] = max(0, G['machineGrip'] - 25)
        G['ibu'] = min(G['ibu'] + 5, G['ibuMax'])
        # Free more cells
        freed = 0
        for i in range(len(G['map'])):
            if G['map'][i] == 'machine' and freed < 8:
                G['map'][i] = 'free'
                freed += 1
        check_phase(G)
        return True

    elif action == 'asa':
        if G.get('sumiBuilt',0) < 3 or G['asaDone']: return False
        G['asaDone'] = True
        G['machineGrip'] = 0
        G['map'] = ['free'] * 64
        G['map'][0] = 'yours'
        return True

    elif action == 'yaka':
        if G['munu'] < 10 or not G['bandits']: return False
        G['munu'] -= 10
        G['bandits'].pop()
        return True

    return False

# ── TUTORIAL CHECKS ──────────────────────────────────────────────────────────

def check_tutorial(G):
    s = G['tutStage']
    if s == 0 and G['farmActions'] >= 1:
        G['tutStage'] = 1
    if s == 1 and G['ibu'] >= 8 and G['sibi'] >= 8:
        G['tutStage'] = 2
    if s == 2 and G['hostActions'] >= 1:
        G['tutStage'] = 3
    if s == 3 and (G['munu'] >= 15 or G['travelersHosted'] >= 3):
        G['tutStage'] = 4
        nid = assign_nima(G)
        G['events'].append(f"[{G['tick']}] NIMA ASSIGNED: {nid}")
    if s == 6 and G['phase'] >= 3:
        G['tutStage'] = 7

def check_phase(G):
    if G['phase'] == 1:
        check_tutorial(G)
    if G['phase'] == 2 and G['tricoCount'] >= 3:
        G['phase'] = 3
        G['events'].append(f"[{G['tick']}] PHASE 3 UNLOCKED (tricoCount={G['tricoCount']})")

# ── TICK ─────────────────────────────────────────────────────────────────────

def tick(G):
    G['tick'] += 1
    t = G['tick']

    # Passive kodu gain
    effective_rate = G['koduRate'] * 0.4 if G['harvestPenalty'] > 0 else G['koduRate']
    G['kodu'] = min(G['kodu'] + effective_rate / TICK_RATE, G['koduMax'])

    # Passive sibi gain
    if G['sibiRate'] > 0:
        G['sibi'] = min(G['sibi'] + G['sibiRate'] / TICK_RATE, G['sibiMax'])

    # Munu decay (phase 1 only)
    if G['phase'] == 1 and t % 150 == 0 and G['munu'] > 0:
        G['munu'] = max(0, G['munu'] - 0.2)

    # Munu decay from feno in later phases (gentle)
    if G['phase'] >= 2 and t % 200 == 0 and G['munu'] > 5:
        G['munu'] = max(0, G['munu'] - 0.1)

    # Harvest penalty countdown
    if G['harvestPenalty'] > 0:
        G['harvestPenalty'] -= 1

    # Kodu shortage - ibu leave
    if G['kodu'] <= 0:
        G['kodu'] = 0
        if t % 60 == 0 and G['ibu'] > 2:
            G['ibu'] = max(2, G['ibu'] - 1)
            G['events'].append(f"[{t}] KODU EMPTY: ibu dropped to {G['ibu']}")

    # Traveler auto-arrive
    travel_interval = max(80, 200 - G['sila'] * 5)
    if G['sila'] >= 5 and t - G['lastTravelerTick'] > travel_interval:
        G['lastTravelerTick'] = t
        G['travelersHosted'] += 1
        G['munu'] = min(G['munu'] + munu_mult(G) * 2, G['munuMax'])
        check_tutorial(G)

    # Tao passive kodu
    if G['nimaId'] == 'tao' and t % 60 == 0:
        G['kodu'] = min(G['kodu'] + 2, G['koduMax'])

    # Dada random events
    if G['nimaId'] == 'dada' and t % 90 == 0:
        r = random.random()
        if r < 0.3:   G['kodu'] = min(G['kodu'] + 15, G['koduMax'])
        elif r < 0.55: G['munu'] = min(G['munu'] + munu_mult(G) * 8, G['munuMax'])
        elif r < 0.75: G['sibi'] = min(G['sibi'] + 8, G['sibiMax'])

    # Bandit drain
    if G['bandits'] and t % 20 == 0:
        G['kodu'] = max(0, G['kodu'] - len(G['bandits']) * 0.3)

    # Machine counter-offensive
    if G['machineGrip'] < 30 and t % 150 == 0:
        reclaim = min(2, G['bolosFree'])
        if reclaim > 0:
            G['bolosFree'] -= reclaim
            G['machineGrip'] = min(100, G['machineGrip'] + reclaim * 2)

    # Staged reveals
    if G['tutStage'] == 5 and G['machineRevealAt'] and t >= G['machineRevealAt']:
        G['machineRevealAt'] = None
        G['events'].append(f"[{t}] MACHINE REVEALED")
    if G['tutStage'] == 5 and G['exchangeRevealAt'] and t >= G['exchangeRevealAt']:
        G['exchangeRevealAt'] = None
        G['tutStage'] = 6
        G['events'].append(f"[{t}] EXCHANGE REVEALED (stage 6)")

    # Random events (phase 2+ only)
    if G['phase'] >= 2 and t - G['lastEventTick'] > 600 and t > 400:
        if random.random() < 0.012:
            G['lastEventTick'] = t
            trigger_event(G)

    # Sumi secession drain
    if G['sumiSeceding'] and t % 40 == 0:
        if G['munu'] >= 3:
            G['munu'] -= 3
        else:
            if G['sumiCount'] > 0:
                G['sumiCount'] -= 1
                G['machineGrip'] = min(100, G['machineGrip'] + 20)
                G['sumiSeceding'] = False
                G['events'].append(f"[{t}] SUMI SECEDED: sumiCount={G['sumiCount']}")

def trigger_event(G):
    t = G['tick']
    evs = ['harvest', 'travelerTrouble']
    if G['ibu'] > 10 and G['phase'] >= 2: evs.append('ibuSplit')
    if G['phase'] == 2 and G['tricoCount'] >= 1: evs.append('bandit')
    if G['phase'] >= 3 and G['sumiCount'] >= 1 and not G['sumiSeceding']: evs.append('sumiSecession')

    ev = random.choice(evs)
    if ev == 'harvest':
        G['harvestPenalty'] = 400
        G['events'].append(f"[{t}] EVENT: bad harvest")
    elif ev == 'travelerTrouble':
        cost = min(int(G['kodu'] * 0.08 + 5), int(G['kodu']))
        G['kodu'] = max(0, G['kodu'] - cost)
        G['sila'] = max(0, G['sila'] - 4)
        G['events'].append(f"[{t}] EVENT: traveler trouble (-{cost} kodu)")
    elif ev == 'ibuSplit':
        lost = 2 if G['ibu'] > 15 else 1
        G['ibu'] = max(3, G['ibu'] - lost)
        G['munu'] = max(0, G['munu'] - 4)
        G['events'].append(f"[{t}] EVENT: ibu split (-{lost} ibu)")
    elif ev == 'bandit':
        G['bandits'].append('bandit')
        G['events'].append(f"[{t}] EVENT: bandit appears")
    elif ev == 'sumiSecession':
        G['sumiSeceding'] = True
        G['events'].append(f"[{t}] EVENT: sumi secession begins")

# ── MAIN LOOP ────────────────────────────────────────────────────────────────

def secs(t): return t / TICK_RATE

def run():
    G = new_game()
    last_action_tick = -5
    action_cooldown = 3  # ticks between actions

    print("=== bolo'bolo SIMULATION ===\n")
    print(f"{'tick':>6} {'time':>6} {'tut':>3} {'ph':>2} {'ibu':>4} {'kodu':>6} {'sibi':>5} {'munu':>5} {'sila':>5} {'grip':>5} | event")
    print("-" * 90)

    def row(label=""):
        print(f"{G['tick']:>6} {secs(G['tick']):>5.0f}s {G['tutStage']:>3} {G['phase']:>2} "
              f"{G['ibu']:>4.0f} {G['kodu']:>6.1f} {G['sibi']:>5.1f} {G['munu']:>5.1f} "
              f"{G['sila']:>5.1f} {G['machineGrip']:>5.1f} | {label}")

    for _ in range(MAX_TICKS):
        tick(G)
        t = G['tick']

        # Flush notable events
        while G['events']:
            ev = G['events'].pop(0)
            row(ev.split('] ', 1)[-1])

        # AI takes an action every few ticks
        if t - last_action_tick >= action_cooldown:
            action = ai_action(G)
            if action and do_action(G, action):
                last_action_tick = t
                # Log key actions
                if action in ('farm','sibi','ibu','trico','tega','sumi','asa','yaka') or \
                   (action == 'host' and G['travelersHosted'] % 5 == 0) or \
                   (action == 'munu' and G['munu'] > 25):
                    row(f"ACTION: {action} → ibu={G['ibu']:.0f} kodu={G['kodu']:.1f} sibi={G['sibi']:.1f} munu={G['munu']:.1f} trico={G['tricoCount']} tega={G['tegaCount']} sumi={G['sumiCount']}")

        # Periodic state snapshots
        if t % DEBUG_INTERVAL == 0:
            row(f"--- nima={G['nimaId']} farmLv={G['farmLv']} sibiLv={G['sibiLv']} feno={G['feno']} trico={G['tricoCount']} tega={G['tegaCount']} sumi={G['sumiCount']} bandits={len(G['bandits'])}")

        # Win condition
        if G['asaDone']:
            row("*** ASA'DALA — THE MACHINE IS GONE ***")
            print(f"\n=== GAME WON at tick {t} ({secs(t):.0f}s / {secs(t)/60:.1f}min) ===")
            print(f"    nima: {G['nimaId']}")
            print(f"    ibu: {G['ibu']:.0f}, travelers hosted: {G['travelersHosted']}")
            print(f"    farmLv: {G['farmLv']}, sibiLv: {G['sibiLv']}, feno: {G['feno']}")
            break
    else:
        row("*** TIMED OUT ***")
        print(f"\n=== GAME INCOMPLETE at tick {t} — phase={G['phase']} tuto={G['tutStage']} ===")
        print(f"    trico={G['tricoCount']} tega={G['tegaCount']} sumi={G['sumiCount']}")
        print(f"    munu={G['munu']:.1f} machineGrip={G['machineGrip']:.1f}")

run()
