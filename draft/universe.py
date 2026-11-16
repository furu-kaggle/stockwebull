"""Ticker universe for the security / quantum sector work.

group:
  pure   - the sector is essentially the whole business
  mixed  - the sector is a meaningful part, but not the whole business
  mega   - mega-cap / conglomerate where the sector is one of many drivers
  etf    - sector ETF (reference)
  bench  - market benchmark
"""

UNIVERSE = [
    # symbol, sector, group, note
    ("CRWD", "security", "pure", "Endpoint / XDR platform"),
    ("PANW", "security", "pure", "Network + cloud + SOC platform (acquired CyberArk)"),
    ("FTNT", "security", "pure", "Firewall / SASE appliances"),
    ("ZS", "security", "pure", "Zero trust / SSE"),
    ("NTSK", "security", "pure", "Netskope: SSE / SASE"),
    ("OKTA", "security", "pure", "Identity"),
    ("SAIL", "security", "pure", "SailPoint: identity governance"),
    ("S", "security", "pure", "SentinelOne: endpoint / XDR"),
    ("CHKP", "security", "pure", "Check Point: firewall"),
    ("RBRK", "security", "pure", "Rubrik: data security / backup"),
    ("VRNS", "security", "pure", "Varonis: data security"),
    ("QLYS", "security", "pure", "Qualys: vulnerability management"),
    ("TENB", "security", "pure", "Tenable: exposure management"),
    ("RPD", "security", "pure", "Rapid7: vulnerability management / SIEM"),
    ("GEN", "security", "pure", "Gen Digital: consumer security (Norton)"),
    ("RDWR", "security", "pure", "Radware: DDoS / WAF"),
    ("OSPN", "security", "pure", "OneSpan: authentication"),
    ("NET", "security", "mixed", "Cloudflare: CDN + zero trust + developer platform"),
    ("AKAM", "security", "mixed", "Akamai: CDN + security + cloud compute"),
    ("FFIV", "security", "mixed", "F5: application delivery + security"),
    ("ATEN", "security", "mixed", "A10 Networks: application delivery + DDoS"),
    ("BB", "security", "mixed", "BlackBerry: secure comms + QNX embedded OS"),
    ("CIBR", "security", "etf", "First Trust NASDAQ Cybersecurity ETF"),
    ("HACK", "security", "etf", "Amplify Cybersecurity ETF"),
    ("BUG", "security", "etf", "Global X Cybersecurity ETF"),

    ("IONQ", "quantum", "pure", "Trapped-ion hardware"),
    ("QNT", "quantum", "pure", "Quantinuum: trapped-ion hardware (Honeywell spin-out)"),
    ("RGTI", "quantum", "pure", "Rigetti: superconducting hardware"),
    ("QBTS", "quantum", "pure", "D-Wave: annealing + gate-model"),
    ("INFQ", "quantum", "pure", "Infleqtion: neutral-atom hardware / sensing"),
    ("XNDU", "quantum", "pure", "Xanadu: photonic hardware"),
    ("QUBT", "quantum", "pure", "Quantum Computing Inc: photonics"),
    ("ARQQ", "quantum", "pure", "Arqit: quantum-safe encryption"),
    ("LAES", "quantum", "pure", "SEALSQ: post-quantum chips"),
    ("BTQ", "quantum", "pure", "BTQ: post-quantum crypto"),
    ("QTUM", "quantum", "etf", "Defiance Quantum ETF"),

    ("GOOGL", "both", "mega", "Quantum AI (Willow) + Google Cloud security (Mandiant, Wiz)"),
    ("MSFT", "both", "mega", "Security business (Defender/Entra/Sentinel) + Azure Quantum"),
    ("IBM", "both", "mega", "IBM Quantum + security software/services"),
    ("AMZN", "both", "mega", "AWS Braket / Ocelot chip + AWS security services"),
    ("NVDA", "quantum", "mega", "CUDA-Q / quantum-GPU hybrid tooling"),
    ("HON", "quantum", "mega", "Majority owner of Quantinuum"),
    ("CSCO", "security", "mega", "Security + Splunk within networking"),
    ("AVGO", "security", "mega", "Symantec / Carbon Black within semis + VMware"),

    ("QQQ", "market", "bench", "Nasdaq-100"),
    ("SPY", "market", "bench", "S&P 500"),
]

# Access to restricted frontier cyber models (vetted-access programs), from public reporting as of 2026-11-16.
#   glasswing : Anthropic Project Glasswing (Claude Mythos)  - launch partners Apr 2026, expansion Jun 2026
#   tac       : OpenAI Trusted Access for Cyber (GPT-5.x-Cyber) - direct model access
#   daybreak  : OpenAI Daybreak Defense Network - partner listing; direct model access not confirmed
# Names not listed here: no public evidence found (not the same as confirmed absence).
AI_ACCESS = {
    "CRWD": ["glasswing", "tac", "daybreak"],
    "PANW": ["glasswing", "tac", "daybreak"],
    "OKTA": ["glasswing", "daybreak"],        # Glasswing expansion per FT report
    "NTSK": ["glasswing"],                    # Glasswing expansion per CyberScoop sources
    "RBRK": ["glasswing"],                    # Glasswing expansion per CyberScoop sources
    "NET": ["tac", "daybreak"],
    "ZS": ["tac", "daybreak"],
    "S": ["tac", "daybreak"],
    "CHKP": ["tac", "daybreak"],
    "FTNT": ["daybreak"],
    "TENB": ["daybreak"],
    "AKAM": ["daybreak"],
}
