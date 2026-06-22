#!/usr/bin/env python3
"""Generate a 100-row test dataset with diverse PII across multiple categories."""

import csv
import random
import os

random.seed(42)

# --- Data pools ---

FIRST_NAMES = {
    "US": ["James", "Mary", "Robert", "Patricia", "Michael", "Jennifer", "William", "Linda"],
    "UK": ["Oliver", "Amelia", "George", "Isla", "Harry", "Freya", "Jack", "Emily"],
    "Finland": ["Mikko", "Aino", "Juhani", "Sari", "Antti", "Kaisa", "Pekka", "Minna"],
    "Germany": ["Lukas", "Anna", "Felix", "Lena", "Maximilian", "Sophie", "Paul", "Marie"],
    "France": ["Lucas", "Emma", "Louis", "Chloé", "Gabriel", "Léa", "Raphaël", "Manon"],
    "Brazil": ["João", "Ana", "Pedro", "Maria", "Lucas", "Juliana", "Mateus", "Fernanda"],
    "India": ["Arjun", "Priya", "Vikram", "Ananya", "Rohan", "Deepika", "Aditya", "Meera"],
    "Japan": ["Haruto", "Yui", "Sota", "Hina", "Ren", "Sakura", "Kaito", "Aoi"],
    "Mexico": ["Santiago", "Valentina", "Mateo", "Regina", "Sebastián", "Camila", "Diego", "Sofía"],
    "Spain": ["Hugo", "Lucía", "Martín", "Sofía", "Daniel", "María", "Pablo", "Carmen"],
    "Italy": ["Leonardo", "Aurora", "Francesco", "Giulia", "Alessandro", "Sofia", "Lorenzo", "Alice"],
    "Netherlands": ["Daan", "Emma", "Sem", "Julia", "Lucas", "Sophie", "Levi", "Mila"],
    "South Korea": ["Min-jun", "Seo-yeon", "Seo-jun", "Ha-yun", "Do-yun", "Ji-yu", "Ye-jun", "Seo-ah"],
    "Australia": ["Oliver", "Charlotte", "Noah", "Amelia", "Jack", "Olivia", "William", "Isla"],
    "Canada": ["Liam", "Olivia", "Noah", "Emma", "Ethan", "Sophia", "Benjamin", "Ava"],
}

LAST_NAMES = {
    "US": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Davis", "Wilson", "Anderson"],
    "UK": ["Wilson", "Taylor", "Davies", "Evans", "Thomas", "Roberts", "Walker", "Clarke"],
    "Finland": ["Virtanen", "Korhonen", "Nieminen", "Mäkinen", "Hämäläinen", "Laine", "Heikkinen", "Koskinen"],
    "Germany": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Wagner", "Becker", "Hoffmann"],
    "France": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Moreau"],
    "Brazil": ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Almeida", "Pereira"],
    "India": ["Sharma", "Patel", "Gupta", "Singh", "Kumar", "Mehta", "Reddy", "Nair"],
    "Japan": ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura"],
    "Mexico": ["García", "Hernández", "López", "Martínez", "González", "Rodríguez", "Pérez", "Sánchez"],
    "Spain": ["García", "Fernández", "López", "Martínez", "González", "Rodríguez", "Sánchez", "Pérez"],
    "Italy": ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci"],
    "Netherlands": ["de Jong", "Jansen", "de Vries", "van den Berg", "van Dijk", "Bakker", "Visser", "Smit"],
    "South Korea": ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon"],
    "Australia": ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Johnson", "White"],
    "Canada": ["Smith", "Brown", "Tremblay", "Martin", "Roy", "Wilson", "MacDonald", "Taylor"],
}

COUNTRIES = list(FIRST_NAMES.keys())

REGIONS = {
    "US": ["California", "Texas", "New York", "Florida", "Illinois", "Pennsylvania", "Ohio", "Georgia"],
    "UK": ["England", "Scotland", "Wales", "Northern Ireland", "London", "Yorkshire", "Lancashire", "Kent"],
    "Finland": ["Uusimaa", "Pirkanmaa", "Varsinais-Suomi", "Pohjois-Pohjanmaa", "Keski-Suomi", "Satakunta", "Lappi", "Häme"],
    "Germany": ["Bavaria", "Baden-Württemberg", "North Rhine-Westphalia", "Hesse", "Saxony", "Berlin", "Hamburg", "Lower Saxony"],
    "France": ["Île-de-France", "Provence-Alpes-Côte d'Azur", "Occitanie", "Auvergne-Rhône-Alpes", "Nouvelle-Aquitaine", "Brittany", "Normandy", "Grand Est"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Minas Gerais", "Bahia", "Paraná", "Rio Grande do Sul", "Pernambuco", "Ceará"],
    "India": ["Maharashtra", "Karnataka", "Tamil Nadu", "Delhi", "Kerala", "Gujarat", "West Bengal", "Rajasthan"],
    "Japan": ["Tokyo", "Osaka", "Kanagawa", "Aichi", "Hokkaido", "Fukuoka", "Hyogo", "Saitama"],
    "Mexico": ["Mexico City", "Jalisco", "Nuevo León", "Puebla", "Guanajuato", "Veracruz", "Chihuahua", "Yucatán"],
    "Spain": ["Madrid", "Catalonia", "Andalusia", "Valencia", "Galicia", "Basque Country", "Castile and León", "Canary Islands"],
    "Italy": ["Lombardy", "Lazio", "Campania", "Sicily", "Veneto", "Piedmont", "Emilia-Romagna", "Tuscany"],
    "Netherlands": ["North Holland", "South Holland", "North Brabant", "Gelderland", "Utrecht", "Overijssel", "Limburg", "Friesland"],
    "South Korea": ["Seoul", "Gyeonggi", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Ulsan"],
    "Australia": ["New South Wales", "Victoria", "Queensland", "Western Australia", "South Australia", "Tasmania", "ACT", "Northern Territory"],
    "Canada": ["Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba", "Saskatchewan", "Nova Scotia", "New Brunswick"],
}

STREETS = {
    "US": ["{n} Oak Street", "{n} Maple Avenue", "{n} Pine Drive", "{n} Cedar Lane", "{n} Elm Road", "{n} Washington Blvd", "{n} Lincoln Parkway", "{n} Jefferson Court"],
    "UK": ["{n} High Street", "{n} Church Lane", "{n} Station Road", "{n} Park Avenue", "{n} Victoria Terrace", "{n} Kings Road", "{n} Queens Drive", "{n} Mill Lane"],
    "Finland": ["Mannerheimintie {n}", "Hämeentie {n}", "Aleksanterinkatu {n}", "Fredrikinkatu {n}", "Kaivokatu {n}", "Bulevardi {n}", "Runeberginkatu {n}", "Mechelininkatu {n}"],
    "Germany": ["Hauptstraße {n}", "Berliner Straße {n}", "Bahnhofstraße {n}", "Gartenweg {n}", "Schillerstraße {n}", "Mozartstraße {n}", "Beethovenallee {n}", "Goethestraße {n}"],
    "France": ["{n} Rue de la Paix", "{n} Avenue des Champs", "{n} Boulevard Haussmann", "{n} Rue Victor Hugo", "{n} Place de la République", "{n} Rue Molière", "{n} Allée des Tilleuls", "{n} Rue Pasteur"],
    "Brazil": ["Rua das Flores {n}", "Avenida Brasil {n}", "Rua São Paulo {n}", "Avenida Paulista {n}", "Rua Augusta {n}", "Travessa do Comércio {n}", "Alameda Santos {n}", "Rua Oscar Freire {n}"],
    "India": ["{n} MG Road", "{n} Gandhi Nagar", "{n} Nehru Street", "{n} Patel Road", "{n} Tagore Lane", "{n} Bose Avenue", "{n} Rajaji Road", "{n} Tilak Marg"],
    "Japan": ["{n}-chōme Shibuya", "{n}-chōme Shinjuku", "{n}-chōme Ginza", "{n}-chōme Roppongi", "{n}-chōme Akasaka", "{n}-chōme Azabu", "{n}-chōme Meguro", "{n}-chōme Setagaya"],
    "Mexico": ["Calle Reforma {n}", "Avenida Juárez {n}", "Calle Hidalgo {n}", "Boulevard Insurgentes {n}", "Calle Morelos {n}", "Avenida Revolución {n}", "Calle Zapata {n}", "Paseo de la Reforma {n}"],
    "Spain": ["Calle Mayor {n}", "Avenida de la Constitución {n}", "Calle Gran Vía {n}", "Paseo del Prado {n}", "Calle Cervantes {n}", "Plaza de España {n}", "Calle Goya {n}", "Rambla de Catalunya {n}"],
    "Italy": ["Via Roma {n}", "Via Garibaldi {n}", "Corso Italia {n}", "Via Dante {n}", "Piazza San Marco {n}", "Via Manzoni {n}", "Viale Europa {n}", "Via Verdi {n}"],
    "Netherlands": ["Keizersgracht {n}", "Herengracht {n}", "Prinsengracht {n}", "Damrak {n}", "Kalverstraat {n}", "Leidsestraat {n}", "Vijzelstraat {n}", "Rokin {n}"],
    "South Korea": ["{n}-gil Gangnam-daero", "{n}-gil Teheran-ro", "{n}-gil Sejong-daero", "{n}-gil Yeouido-dong", "{n}-gil Jongno", "{n}-gil Samseong-ro", "{n}-gil Apgujeong-ro", "{n}-gil Bukchon-ro"],
    "Australia": ["{n} George Street", "{n} Collins Street", "{n} Pitt Street", "{n} Flinders Lane", "{n} Queen Street", "{n} Murray Street", "{n} King William Road", "{n} Hay Street"],
    "Canada": ["{n} Yonge Street", "{n} Rue Sainte-Catherine", "{n} Robson Street", "{n} Jasper Avenue", "{n} Portage Avenue", "{n} Barrington Street", "{n} King Street", "{n} Sparks Street"],
}

POLITICAL_PARTIES = {
    "US": ["Democratic Party", "Republican Party", "Libertarian Party", "Green Party", "Independent"],
    "UK": ["Conservative", "Labour", "Liberal Democrats", "Green Party", "SNP"],
    "Finland": ["SDP", "Kokoomus", "Keskusta", "Perussuomalaiset", "Vihreät", "Vasemmistoliitto"],
    "Germany": ["CDU", "SPD", "Grüne", "FDP", "AfD", "Die Linke"],
    "France": ["Renaissance", "Rassemblement National", "La France Insoumise", "Les Républicains", "EELV"],
    "Brazil": ["PT", "PL", "PSDB", "MDB", "PSOL", "Novo"],
    "India": ["BJP", "INC", "AAP", "TMC", "DMK", "BSP"],
    "Japan": ["LDP", "CDP", "Komeito", "JCP", "Nippon Ishin", "DPP"],
    "Mexico": ["Morena", "PAN", "PRI", "PRD", "Movimiento Ciudadano"],
    "Spain": ["PSOE", "PP", "Vox", "Sumar", "ERC", "Podemos"],
    "Italy": ["Fratelli d'Italia", "PD", "Lega", "Forza Italia", "M5S"],
    "Netherlands": ["VVD", "PVV", "NSC", "GL-PvdA", "D66", "BBB"],
    "South Korea": ["PPP", "DPK", "Justice Party", "Reform Party"],
    "Australia": ["Labor", "Liberal", "Nationals", "Greens", "One Nation"],
    "Canada": ["Liberal", "Conservative", "NDP", "Bloc Québécois", "Green Party"],
}

RELIGIONS = ["Christianity", "Islam", "Hinduism", "Buddhism", "Judaism", "Sikhism", "Atheism", "Agnosticism", "Shinto", "Taoism", "None", "Prefer not to say"]
SEXES = ["Male", "Female", "Non-binary", "Prefer not to say"]
ORIENTATIONS = ["Heterosexual", "Homosexual", "Bisexual", "Pansexual", "Asexual", "Prefer not to say"]
ETHNICITIES = ["White", "Black", "Hispanic/Latino", "Asian", "Middle Eastern", "Indigenous", "Mixed", "Pacific Islander", "South Asian", "Southeast Asian", "Prefer not to say"]

DIAGNOSES = [
    "Type 2 diabetes mellitus", "Essential hypertension", "Major depressive disorder",
    "Generalized anxiety disorder", "Asthma", "COPD", "Atrial fibrillation",
    "Hypothyroidism", "Hyperlipidemia", "Osteoarthritis", "Chronic kidney disease",
    "Migraine", "GERD", "Rheumatoid arthritis", "Psoriasis", "Bipolar disorder",
    "PTSD", "Epilepsy", "Crohn's disease", "Ulcerative colitis", "HIV positive",
    "Hepatitis C", "Lupus", "Multiple sclerosis", "Parkinson's disease",
    "Celiac disease", "Fibromyalgia", "Sleep apnea", "Anemia", "None",
]

MEDICATIONS = [
    "Metformin 500mg", "Lisinopril 10mg", "Sertraline 50mg", "Atorvastatin 20mg",
    "Levothyroxine 75mcg", "Amlodipine 5mg", "Omeprazole 20mg", "Metoprolol 25mg",
    "Albuterol inhaler", "Ibuprofen 400mg", "Gabapentin 300mg", "Prednisone 10mg",
    "Warfarin 5mg", "Insulin glargine", "Escitalopram 10mg", "Duloxetine 30mg",
    "Alprazolam 0.5mg", "Tramadol 50mg", "Montelukast 10mg", "None",
]

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

DISABILITY_STATUS = ["None", "Visual impairment", "Hearing impairment", "Mobility impairment",
                     "Chronic pain condition", "Cognitive disability", "Prefer not to say"]

GENETIC_MARKERS = ["BRCA1 positive", "BRCA2 positive", "Factor V Leiden carrier",
                   "Sickle cell trait", "Cystic fibrosis carrier", "APOE4 homozygous",
                   "HLA-B27 positive", "None detected", "Not tested", "Thalassemia minor"]

MENTAL_HEALTH = ["No conditions", "Depression (treated)", "Anxiety (treated)",
                 "ADHD (diagnosed)", "Bipolar (managed)", "OCD (treated)",
                 "PTSD (in therapy)", "Eating disorder (recovered)", "None disclosed"]


def gen_email(first: str, last: str, country: str) -> str:
    # RFC 2606 reserved domains only — synthetic test data must never resolve
    # to a real mailbox. Multiple TLDs preserve country/domain-shape variety.
    pool = ["example.com", "example.org", "example.net"]
    domains = {c: pool for c in [
        "US", "UK", "Finland", "Germany", "France", "Brazil", "India", "Japan",
        "Mexico", "Spain", "Italy", "Netherlands", "South Korea", "Australia", "Canada",
    ]}
    sep = random.choice([".", "_", ""])
    f = first.lower().replace("é", "e").replace("ö", "o").replace("ä", "a").replace("ü", "u").replace("-", "")
    l = last.lower().replace("é", "e").replace("ö", "o").replace("ä", "a").replace("ü", "u").replace(" ", "").replace("-", "")
    domain = random.choice(domains.get(country, ["gmail.com"]))
    num = random.choice(["", str(random.randint(1, 99))])
    return f"{f}{sep}{l}{num}@{domain}"


def gen_phone(country: str) -> str:
    formats = {
        "US": lambda: f"+1 ({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
        "UK": lambda: f"+44 {random.choice(['20','7','77'])}{random.randint(10,99)} {random.randint(100,999)} {random.randint(1000,9999)}",
        "Finland": lambda: f"+358 {random.choice(['40','44','45','50'])} {random.randint(1000000,9999999)}",
        "Germany": lambda: f"+49 {random.choice(['151','152','160','170','171','175','176','177','178','179'])} {random.randint(1000000,99999999)}",
        "France": lambda: f"+33 {random.choice(['6','7'])}{random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}",
        "Brazil": lambda: f"+55 {random.randint(11,99)} 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
        "India": lambda: f"+91 {random.choice(['6','7','8','9'])}{random.randint(100000000,999999999)}",
        "Japan": lambda: f"+81 {random.choice(['70','80','90'])}-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
        "Mexico": lambda: f"+52 {random.randint(10,99)} {random.randint(1000,9999)} {random.randint(1000,9999)}",
        "Spain": lambda: f"+34 {random.choice(['6','7'])}{random.randint(10,99)} {random.randint(100,999)} {random.randint(100,999)}",
        "Italy": lambda: f"+39 3{random.randint(10,99)} {random.randint(100,999)} {random.randint(1000,9999)}",
        "Netherlands": lambda: f"+31 6 {random.randint(10000000,99999999)}",
        "South Korea": lambda: f"+82 10-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
        "Australia": lambda: f"+61 4{random.randint(10,99)} {random.randint(100,999)} {random.randint(100,999)}",
        "Canada": lambda: f"+1 ({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
    }
    return formats.get(country, formats["US"])()


def gen_national_id(country: str) -> str:
    generators = {
        "US": lambda: f"{random.randint(100,899)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
        "UK": lambda: f"{random.choice('ABCEGHJKLMNPRSTWXYZ')}{random.choice('ABCEGHJKLMNPRSTWXYZ')} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.choice('ABCD')}",
        "Finland": lambda: f"{random.randint(1,28):02d}{random.randint(1,12):02d}{random.randint(50,99)}-{random.randint(2,899):03d}{random.choice('0123456789ABCDEFHJKLMNPRSTUVWXY')}",
        "Germany": lambda: f"Steuer-ID: {random.randint(10000000000,99999999999)}",
        "France": lambda: f"{random.choice('12')} {random.randint(50,99):02d} {random.randint(1,12):02d} {random.randint(1,95):02d} {random.randint(1,999):03d} {random.randint(1,999):03d} {random.randint(1,99):02d}",
        "Brazil": lambda: f"{random.randint(100,999)}.{random.randint(100,999)}.{random.randint(100,999)}-{random.randint(10,99)}",
        "India": lambda: f"{random.randint(2000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)}",
        "Japan": lambda: f"My Number: {random.randint(100000000000,999999999999)}",
        "Mexico": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))}{random.randint(600000,999999)}{'HM'[random.randint(0,1)]}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5))}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=1))}{random.randint(0,9)}",
        "Spain": lambda: f"{random.randint(10000000,99999999)}{'TRWAGMYFPDXBNJZSQVHLCKE'[random.randint(0,22)]}",
        "Italy": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=6))}{random.randint(50,99)}{'AEHLMPRST'[random.randint(0,8)]}{random.randint(1,28):02d}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=1))}{random.randint(100,999)}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=1))}",
        "Netherlands": lambda: f"BSN: {random.randint(100000000,999999999)}",
        "South Korea": lambda: f"{random.randint(500101,991231)}-{random.choice('1234')}{random.randint(100000,999999)}",
        "Australia": lambda: f"TFN: {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}",
        "Canada": lambda: f"{random.randint(100,999)}-{random.randint(100,999)}-{random.randint(100,999)}",
    }
    return generators.get(country, generators["US"])()


def gen_bank_account(country: str) -> str:
    iban_prefixes = {
        "UK": ("GB", 22), "Finland": ("FI", 18), "Germany": ("DE", 22),
        "France": ("FR", 27), "Spain": ("ES", 24), "Italy": ("IT", 27),
        "Netherlands": ("NL", 18), "Brazil": ("BR", 29),
    }
    if country in iban_prefixes:
        prefix, length = iban_prefixes[country]
        digits_needed = length - len(prefix)
        return f"{prefix}{''.join([str(random.randint(0,9)) for _ in range(digits_needed)])}"
    elif country == "US":
        return f"Routing: {random.randint(100000000,999999999)}, Acct: {random.randint(1000000000,9999999999)}"
    elif country == "Canada":
        return f"{random.randint(10000,99999)}-{random.randint(100,999)}-{random.randint(1000000,9999999)}"
    elif country == "India":
        bank_codes = ["SBIN", "HDFC", "ICIC", "UTIB", "PUNB"]
        return f"IFSC: {random.choice(bank_codes)}0{random.randint(100000,999999)}, Acct: {random.randint(10000000000,99999999999)}"
    elif country == "Japan":
        return f"Bank: {random.randint(1000,9999)}, Branch: {random.randint(100,999)}, Acct: {random.randint(1000000,9999999)}"
    elif country == "Australia":
        return f"BSB: {random.randint(100,999)}-{random.randint(100,999)}, Acct: {random.randint(100000,999999)}"
    elif country in ("South Korea", "Mexico"):
        return f"{random.randint(1000,9999)}-{random.randint(100,999)}-{random.randint(100000,999999)}"
    return f"ACCT-{random.randint(10000000,99999999)}"


def gen_passport(country: str) -> str:
    formats = {
        "US": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=1))}{random.randint(10000000,99999999)}",
        "UK": lambda: f"{random.randint(100000000,999999999)}",
        "Finland": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(1000000,9999999)}",
        "Germany": lambda: f"{''.join(random.choices('CFGHJKLMNPRTVWXYZ0123456789', k=10))}",
        "France": lambda: f"{random.randint(10,99)}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(10000,99999)}",
        "Brazil": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(100000,999999)}",
        "India": lambda: f"{''.join(random.choices('JKLMNPRSTUVWXYZ', k=1))}{random.randint(1000000,9999999)}",
        "Japan": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(1000000,9999999)}",
        "Mexico": lambda: f"{random.randint(1000000000,9999999999)}",
        "Spain": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=3))}{random.randint(100000,999999)}",
        "Italy": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(1000000,9999999)}",
        "Netherlands": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))}{random.randint(0,9)}",
        "South Korea": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=1))}{random.randint(10000000,99999999)}",
        "Australia": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(1000000,9999999)}",
        "Canada": lambda: f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=2))}{random.randint(100000,999999)}",
    }
    return formats.get(country, formats["US"])()


def gen_dob() -> str:
    year = random.randint(1940, 2005)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    fmt = random.choice(["us", "eu", "iso"])
    if fmt == "us":
        return f"{month:02d}/{day:02d}/{year}"
    elif fmt == "eu":
        return f"{day:02d}/{month:02d}/{year}"
    else:
        return f"{year}-{month:02d}-{day:02d}"


def gen_credit_card() -> str:
    prefix = random.choice(["4", "5", "37", "6011"])
    remaining = 16 - len(prefix) - 1
    body = prefix + "".join([str(random.randint(0, 9)) for _ in range(remaining)])
    # Simple Luhn check digit
    digits = [int(d) for d in body]
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    check = (10 - sum(digits) % 10) % 10
    return body + str(check)


def gen_ip() -> str:
    return f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def gen_salary() -> str:
    currency_map = {
        "US": "$", "UK": "£", "Finland": "€", "Germany": "€", "France": "€",
        "Brazil": "R$", "India": "₹", "Japan": "¥", "Mexico": "MXN ",
        "Spain": "€", "Italy": "€", "Netherlands": "€", "South Korea": "₩",
        "Australia": "A$", "Canada": "C$",
    }
    country = random.choice(COUNTRIES)
    symbol = currency_map.get(country, "$")
    amount = random.randint(25000, 250000)
    return f"{symbol}{amount:,}"


def generate_rows(n: int = 100) -> list[dict]:
    rows = []
    for i in range(n):
        country = random.choice(COUNTRIES)
        first = random.choice(FIRST_NAMES[country])
        last = random.choice(LAST_NAMES[country])
        sex = random.choice(SEXES)

        row = {
            "id": i + 1,
            "full_name": f"{first} {last}",
            "date_of_birth": gen_dob(),
            "age": random.randint(18, 95),
            "sex": sex,
            "sexual_orientation": random.choice(ORIENTATIONS),
            "ethnicity": random.choice(ETHNICITIES),
            "religion": random.choice(RELIGIONS),
            "political_party": random.choice(POLITICAL_PARTIES[country]),
            "country": country,
            "region": random.choice(REGIONS[country]),
            "address": random.choice(STREETS[country]).format(n=random.randint(1, 999)),
            "email": gen_email(first, last, country),
            "phone": gen_phone(country),
            "national_id": gen_national_id(country),
            "passport_number": gen_passport(country),
            "bank_account": gen_bank_account(country),
            "credit_card": gen_credit_card(),
            "annual_salary": gen_salary(),
            "ip_address": gen_ip(),
            "diagnosis_primary": random.choice(DIAGNOSES),
            "diagnosis_secondary": random.choice(DIAGNOSES),
            "current_medication": random.choice(MEDICATIONS),
            "blood_type": random.choice(BLOOD_TYPES),
            "disability_status": random.choice(DISABILITY_STATUS),
            "genetic_markers": random.choice(GENETIC_MARKERS),
            "mental_health_status": random.choice(MENTAL_HEALTH),
            "emergency_contact_name": f"{random.choice(FIRST_NAMES[country])} {random.choice(LAST_NAMES[country])}",
            "emergency_contact_phone": gen_phone(country),
        }
        rows.append(row)
    return rows


def main():
    output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(output_dir, "tests", "test_data.csv")

    rows = generate_rows(100)

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} rows with {len(fieldnames)} columns")
    print(f"Columns: {', '.join(fieldnames)}")
    print(f"Countries represented: {sorted(set(r['country'] for r in rows))}")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
