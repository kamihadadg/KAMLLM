"""
One-off generator: writes doc/imperial_history_empires_50pages.pdf (English, A4).
Run from repo root: python scripts/build_imperial_history_pdf.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import fitz  # PyMuPDF

# Structured notes; body text is original summary-style English for sampling / RAG demos.
EMPIRES: list[tuple[str, str, str, str]] = [
    ("What is an empire?", "Concepts", "All periods", "An empire coordinates multiple regions through centralized authority, armies, taxation, law, and symbols of legitimacy. It is not merely size: networks of loyalty, elites, and infrastructure matter as much as conquest."),
    ("Akkadian imperium", "Mesopotamia", "c. 2334–2154 BCE", "Centered in Sumer and Akkad, the state linked city-states under a singular crown, promoting shared administration and monumental messaging. Fragile ecology and frontier pressure later stressed its institutions."),
    ("Old Babylonian reach", "Mesopotamia", "c. 1894–1595 BCE", "Hammurapi’s law stele illustrates imperial integration through codified justice and patron gods. Long-distance trade and diplomacy tied cities to wider West Asian circuits."),
    ("Neo-Assyrian world order", "Near East", "911–609 BCE", "Massive sieges, standing armies, and royal inscriptions projected terror and order. Capitals like Nineveh displayed booty and scholarship even as subject peoples simmered."),
    ("Neo-Babylonian revival", "Mesopotamia", "626–539 BCE", "Nebuchadnezzar’s Babylon blended engineering spectacle with trade control. Priestly and merchant elites anchored urban splendor until Persian conquest."),
    ("Achaemenid Persia", "West & Central Asia", "550–330 BCE", "Satrapies, royal roads, and toleration policies knit diverse nations. Royal centers like Persepolis staged empire as cooperative kingship under Ahura Mazda’s favor."),
    ("Alexander’s campaigns", "Eurasia", "336–323 BCE", "Macedonian phalanx speedily cracked Persian administration, then Greek cities debated loyalty to a living god-king. Sudden death froze a fragile personal monarchy."),
    ("Seleucid sphere", "Hellenistic Asia", "312–63 BCE", "Greek urban foundations sat atop older economies from Syria to Bactria. Dynastic wars and Parthian rise trimmed western Asian Hellenism."),
    ("Parthian Arsacid realm", "Iran & Mesopotamia", "247 BCE – 224 CE", "Heavy cavalry and caravan taxes along Silk Road corridors balanced Roman ambitions in Syria. Court culture blended Iranian titles with Greek city charters eastward."),
    ("Ptolemaic Egypt", "Egypt & coasts", "305–30 BCE", "Alexandria blended pharaonic style with Greek science and banking. Grain exports tied the Nile to Mediterranean politics."),
    ("Maurya unification", "South Asia", "322–185 BCE", "Chandragupta and Ashoka braided Mahajanapadas into a bureaucracy with edicts carved on rocks. Buddhism became a moral language of empire."),
    ("Han consolidation", "China", "206 BCE – 220 CE", "Confucian examination ideals, frontier colonization against steppe peoples, and silk exports shaped agrarian Pax. Peasant uprisals later shattered the dynasty."),
    ("Roman Republic’s expansion", "Mediterranean", "264–31 BCE", "Senatorial ambition and Italian manpower consumed Carthage and Hellenistic kingdoms. Civil wars hinted that scale outgrew republican gears."),
    ("Augustan Principate", "Roman world", "27 BCE – 180 CE", "Emperors sold peace, staged bread and games, regularized armies along rivers. Provincial elites fused local status with Latin culture."),
    ("High empire crises", "Roman world", "180–284 CE", "Barracks emperors, inflation, and plague tested frontiers from Scotland to Mesopotamia. Diocletian’s reforms signaled deeper bureaucratization."),
    ("Late Roman reshaping", "Mediterranean", "284–476 CE west", "Tetrarchy, Constantinople’s rise, and Christianization rewired legitimacy. The western provinces fragmented while the east endured."),
    ("Byzantium under Justinian", "Eastern Mediterranean", "527–565 CE peak", "Reconquests in Italy and Africa aimed to revive Roman universality. Legal codification and Hagia Sophia expressed orthodox Christian empire."),
    ("Byzantine middle centuries", "Eastern Roman", "7th–11th cent.", "Losses to Arabs and Slavs shrank territory yet themes and Greek culture hardened identity. Trade with steppe and Islam enriched Constantinople."),
    ("Rashidun expansion", "Middle East", "632–661 CE", "Arab-led armies seized Syria, Egypt, and Persia while caliphal authority stayed personal. Garrison towns anchored early Islamic rule."),
    ("Umayyad caliphate", "Dar al-Islam", "661–750 CE", "Damascus linked Berber West to Central Asian marches. Arab elite privilege sparked opposition that the Abbasids exploited."),
    ("Abbasid revolution & age", "Middle East", "750–1258 CE", "Baghdad became a round-city hub of paper, translation, and finance. Provincial autonomy and Turkish soldiery later unraveled central power."),
    ("Tang cosmopolitanism", "China", "618–907 CE", "Chang’an hosted Silk Road faiths and poets while equal-field ideas vied with aristocratic clans. An Lushan’s rebellion scarred central control."),
    ("Carolingian experiment", "Western Europe", "751–888 CE", "Charlemagne’s coronation claimed Roman renewal in Frankish guise. Missi dominici and parish networks spread shallow administration."),
    ("Holy Roman Empire", "Central Europe", "962–1806 CE", "Electors, diets, and emperors negotiated a patchwork sovereignty. Habsburg dynasts later tried to steer it toward Spanish and Balkan wars."),
    ("Seljuk Turko-Persian rule", "Middle East", "11th–13th cent.", "Turkic military households patronized Persian bureaucracy and Sunni institutions. They bridged Iraq to Anatolia before Mongol storms."),
    ("Song commercial revolution", "China", "960–1279 CE", "Paper money and urban guilds thrived even as steppe pressure grew. Southern rice frontiers fed dense markets."),
    ("Mongol world empire", "Eurasia", "13th cent.", "Chinggisid princes fused steppe mobility with Chinese and Muslim finance. Pax Mongolica rerouted silk, plague, and knowledge."),
    ("Delhi Sultanate", "North India", "1206–1526 CE", "Turkic war bands introduced iqta administration amid Hindu kingdom resistance. Sufi networks softened cultural edges."),
    ("Mali and gold roads", "West Africa", "13th–16th cent.", "Mansa Musa’s pilgrimage broadcast Malian gold wealth. Timbuktu scholars linked Sudanic states to broader Islamicate learning."),
    ("Aztec tributary system", "Mesoamerica", "1428–1521 CE", "The Triple Alliance extracted labor and goods through flower wars and markets. Spanish conquistadors exploited elite rivalries."),
    ("Inka vertical archipelago", "Andes", "1438–1533 CE", "Quipu bureaucrats and mit’a labor stitched microclimates. Huayna Capac’s epidemics preceded Pizarro’s coup in Cajamarca."),
    ("Ottoman rise", "Anatolia–Balkans", "1299–1453 rise", "Ghazi ideology and timar cavalry fed expansion; cannons took Constantinople. Millet arrangements managed confessional diversity."),
    ("Ottoman classical age", "Mediterranean rim", "16th cent.", "Süleyman’s navy sparred with Habsburgs in the central Med. Devshirme elites balanced ulema and sipahi interests."),
    ("Safavid Persia", "Iran", "1501–1736 CE", "Shi‘i establishment as state religion distinguished Iran from Sunni neighbors. Silk and Armenian trade tied Isfahan to global circuits."),
    ("Mughal synthesis", "South Asia", "1526–1857 CE", "Akbar’s sulh-i kull experimented with religious pluralism. Peacock Throne wealth rested on zamindari and world textile demand."),
    ("Spanish monarchy global", "Iberia & Americas", "1492–1700 CE", "Silver from Potosí fueled Habsburg wars while Castilian law framed conquest. Creole societies emerged under peninsular suspicion."),
    ("Dutch mercantile empire", "World oceans", "17th–18th cent.", "VOC joint-stock violence in Indonesia complemented domestic financial innovation. Tulip bubbles and slave trades linked profit to projection."),
    ("British East India to Raj", "South Asia", "1757–1947 CE", "Plassey’s shock turned trading rights into revenue farming. Victorian railways and census technologies intensified rule before partition debates."),
    ("Russian continental growth", "Eurasian north", "16th–19th cent.", "Siberian fur, Cossack lines, and nobility service state pushed frontiers east. Serfdom’s weight matched military mass."),
    ("Habsburg composite monarchy", "Central Europe", "1526–1918 CE", "Dynastic marriages stacked crowns from Madrid to Prague. Ethnic-national claims eventually overwhelmed dualist bargains."),
    ("Napoleonic reordering", "Europe", "1799–1815 CE", "Civil codes, satellite kingdoms, and continental blockade reorganized elites. Waterloo restored monarchies yet could not erase legal modernity."),
    ("Victorian British world system", "Global", "19th cent.", "Industrial capacity, admiralty coercion, and free-trade ideology structured informal empire alongside settler colonies. Irish and Indian famines haunt its ledger."),
    ("Scramble for Africa frameworks", "Africa", "1880s–1900 CE", "Berlin conference lines on maps ignored linguistic zones. Machine guns, quinine, and concession companies sped occupation."),
    ("Meiji imperial Japan", "East Asia", "1868–1945 CE", "Industrial learning, conscription, and constitutional monarchy enabled overseas wars. Korea and Taiwan became laboratories of control."),
    ("German colonial Kaiserreich", "Africa & Pacific", "1884–1919 CE", "Bismarckian reluctance gave way to acquisitions in Cameroon, SW Africa, and Qingdao. Genocide in Herero lands stains its record."),
    ("US overseas turn", "Americas & Pacific", "1898 onward", "The War with Spain brought Puerto Rico, Guam, and a debate over the Philippines. Dollar diplomacy later complemented bases and corporations."),
    ("Late Ottoman reform", "Middle East", "1839–1922 CE", "Tanzimat and Young Turk constitutionalism struggled with debt commissions and Balkan secessions. WWI ended the sultanate."),
    ("Mandates and Paris principles", "Middle East & Africa", "1919–1940s", "League mandates framed rule as tutelage yet entrenched extractive economics. Anticolonial presses exposed the gap between rhetoric and police power."),
    ("Decolonization waves", "Asia & Africa", "1945–1970s", "UN membership surged as European empires retreated, often after insurgency. Cold War patrons competed to shape new states."),
    ("Legacies in borders and law", "Worldwide", "Longue durée", "Imperial maps ghost in today’s conflicts; legal pluralisms and migration networks inherit colonial switches. Studying empires clarifies how power routinizes difference."),
]

OUT = Path("doc") / "imperial_history_empires_50pages.pdf"


def write_pdf() -> None:
    if len(EMPIRES) != 50:
        raise SystemExit(f"Expected 50 sections, got {len(EMPIRES)}")

    doc = fitz.open()
    page_w, page_h = fitz.paper_rect("a4").width, fitz.paper_rect("a4").height
    margin_x, margin_top, margin_bot = 56, 64, 56
    usable_h = page_h - margin_top - margin_bot
    line_h = 13
    font_body, font_title = "helv", "helv"
    size_body, size_title = 10.5, 14

    for i, (title, region, span, blurb) in enumerate(EMPIRES, start=1):
        page = doc.new_page(width=page_w, height=page_h)
        y = margin_top

        def put_line(text: str, *, bold: bool = False, size: float = size_body) -> bool:
            nonlocal y
            if y > page_h - margin_bot:
                return False
            page.insert_text(
                (margin_x, y),
                text,
                fontsize=size,
                fontname=font_title if bold else font_body,
            )
            y += line_h if size == size_body else line_h * 1.4
            return True

        header = f"Imperial History Reader — Page {i} of 50"
        put_line(header, bold=True, size=size_title)
        y += line_h * 0.3
        put_line(f"{title}", bold=True, size=12)
        put_line(f"Region: {region}    Span: {span}", bold=False, size=10)
        y += line_h * 0.6

        para = (
            f"{blurb} This volume is a compact survey for students; consult specialist "
            "literature for evidence debates, archives, and conflicting chronologies."
        )
        for line in textwrap.wrap(para, width=88):
            if not put_line(line):
                break

        # Fill remaining page space with neutral historiographic boilerplate (demo density).
        filler = (
            "Method note: compare primary inscriptions, coinage, and tax records with "
            "archaeological settlement patterns. Avoid teleology: empires rise through "
            "coalitions, not destiny; they fall when logistics, legitimacy, and ecology "
            "misalign. Teaching tip: map a single commodity—salt, silver, cotton—across "
            "the chapter’s century to reveal hidden dependencies."
        )
        y += line_h * 0.8
        for line in textwrap.wrap(filler, width=88):
            if not put_line(line, size=10):
                break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT, garbage=4, deflate=True)
    doc.close()
    print(f"Wrote {OUT.resolve()} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    write_pdf()
