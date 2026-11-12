"""
API sunmayan bir web sayfasından Python ile veri çekme örneği.

Kaynak site: https://books.toscrape.com/
(Web scraping alıştırması için hazırlanmış, kurgusal bir kitap mağazası.)

Akış:
    0. robots.txt kontrolü
    1. Hızlı yol: pandas.read_html ile tek bir HTML tablosu
    2. Kontrollü yol: requests + BeautifulSoup ile kitap kartları
    3. Sayfalama ve istekler arasında bekleme
    4. Temizleme ve doğrulama, tarihli CSV olarak kaydetme

Çalıştırma:
    pip install -r requirements.txt
    python scraper.py
"""

from __future__ import annotations

import time
from datetime import date
from io import StringIO
from urllib import robotparser
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "medium-ornek-scraper/1.0 (egitim amacli)"}
PUAN = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


# --- Adım 0: İzin kontrolü -------------------------------------------------

def robots_izin_veriyor_mu(url: str, user_agent: str = "*") -> bool:
    """Sitenin robots.txt dosyasına göre url'nin taranabilir olup olmadığını döndürür."""
    rp = robotparser.RobotFileParser(urljoin(url, "/robots.txt"))
    rp.read()
    return rp.can_fetch(user_agent, url)


# --- Adım 1: Hızlı yol — pandas.read_html -----------------------------------

def urun_tablosunu_oku(kitap_url: str) -> pd.DataFrame:
    """Kitap detay sayfasındaki 'Product Information' tablosunu DataFrame olarak döndürür."""
    resp = requests.get(kitap_url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # sunucu charset bildirmiyor; aksi halde '£' -> 'Â£' olur

    tablo = pd.read_html(StringIO(resp.text))[0]
    tablo.columns = ["alan", "deger"]
    return tablo


# --- Adım 2: Kontrollü yol — requests + BeautifulSoup -----------------------

def sayfayi_ayikla(soup: BeautifulSoup, sayfa_url: str) -> list[dict]:
    """Bir liste sayfasındaki tüm kitap kartlarını sözlük listesine çevirir."""
    kitaplar = []
    for kart in soup.select("article.product_pod"):
        link = kart.h3.a
        kitaplar.append({
            "baslik": link["title"],  # görünen metin '...' ile kısaltılmış olabilir
            "url": urljoin(sayfa_url, link["href"]),
            "fiyat": kart.select_one("p.price_color").get_text(strip=True),
            "puan": kart.select_one("p.star-rating")["class"][1],
            "stok": kart.select_one("p.availability").get_text(strip=True),
        })
    return kitaplar


# --- Adım 3: Sayfalama ve "nazik" olmak -------------------------------------

def tum_sayfalari_cek(url: str, bekleme: float = 1.0) -> pd.DataFrame:
    """'next' linkini takip ederek tüm liste sayfalarını dolaşır."""
    satirlar = []
    with requests.Session() as s:
        s.headers.update(HEADERS)
        while url:
            r = s.get(url, timeout=10)
            r.raise_for_status()
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
            satirlar += sayfayi_ayikla(soup, url)
            sonraki = soup.select_one("li.next a")
            url = urljoin(url, sonraki["href"]) if sonraki else None
            time.sleep(bekleme)  # sunucuyu yormamak için
    return pd.DataFrame(satirlar)


# --- Adım 4: Temizleme ve doğrulama -----------------------------------------

def temizle(df: pd.DataFrame) -> pd.DataFrame:
    """Metin sütunlarını analiz edilebilir tiplere çevirir. Kaynakta olmayan değer eklemez."""
    df = df.copy()
    df["fiyat"] = df["fiyat"].str.replace("£", "", regex=False).astype(float)
    df["puan"] = df["puan"].map(PUAN)          # "Three" -> 3
    df["stokta"] = df["stok"].eq("In stock")   # "In stock" -> True
    return df


def dogrula(df: pd.DataFrame, beklenen_satir: int = 1000) -> None:
    """Çekilen verinin tutarlılığını kontrol eder; sorun varsa AssertionError fırlatır."""
    assert len(df) == beklenen_satir, f"{beklenen_satir} satır bekleniyordu, {len(df)} geldi"
    assert df["url"].is_unique, "Aynı kitap iki kez çekilmiş"
    assert df["puan"].notna().all(), "Tanınmayan bir puan değeri var"
    assert df["fiyat"].gt(0).all(), "Sıfır veya negatif fiyat var"


# --- Dinamik sayfalar için (isteğe bağlı) ----------------------------------

def html_playwright_ile(url: str, bekle_secici: str = "table") -> str:
    """JavaScript ile yüklenen sayfalar için. Gerekirse:
    pip install playwright && playwright install chromium
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector(bekle_secici)
        html = page.content()
        browser.close()
    return html


def main() -> None:
    print("robots.txt izin veriyor mu?", robots_izin_veriyor_mu(BASE))

    tablo = urun_tablosunu_oku(BASE + "catalogue/a-light-in-the-attic_1000/index.html")
    print(tablo, end="\n\n")

    print("Liste sayfaları çekiliyor (yaklaşık 1 dakika sürer)...")
    df = temizle(tum_sayfalari_cek(BASE))
    dogrula(df)
    print(df.shape)
    print(df.sample(5, random_state=42)[["baslik", "fiyat", "puan"]])

    dosya = f"kitaplar_{date.today():%Y-%m-%d}.csv"
    df.to_csv(dosya, index=False)
    print(f"Kaydedildi: {dosya}")


if __name__ == "__main__":
    main()
