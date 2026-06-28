import sqlite3

from datetime import datetime, timedelta
import pandas as pd

DB_DOSYA = 'fonlar.db'

def db_baglan():
    return sqlite3.connect(DB_DOSYA)

def kaydet(fon_kodu:str,df:pd.DataFrame):

    conn = db_baglan()

    df_kayit = df[['date','price']].copy()
    df_kayit.columns = ['tarih','fiyat']
    df_kayit['fon_kodu'] = fon_kodu.upper()
    df_kayit['cekildigi_zaman']=datetime.now()

    df_kayit.to_sql('fonlar',conn,if_exists='append',index=False)

    conn.close()

def tablo_olustur():

    conn = db_baglan()
    cursor= conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fonlar(
            fon_kodu TEXT NOT NULL,
            tarih TEXT NOT NULL,
            fiyat REAL NOT NULL,
            cekildigi_zaman TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fon_kodu,tarih)       
                 )               
            """)
    conn.commit()
    conn.close()
    print('Tablo kuruldu')

def cache_oku(fon_kodu:str,gun:int):
    conn=db_baglan()

    bitis = datetime.now().strftime("%Y-%m-%d")
    baslangic = (datetime.now()-timedelta(days=gun)).strftime("%Y-%m-%d")

    query = """
        SELECT tarih,fiyat,cekildigi_zaman
        FROM fonlar
        WHERE fon_kodu = ?
            AND tarih >= ?
            AND tarih <= ?
        ORDER BY tarih
    """
    df = pd.read_sql_query(query,conn, params=(fon_kodu.upper(),baslangic,bitis))
    conn.close()

    if df.empty:
        return None
    
    return df

def cache_guncel(df:pd.DataFrame, max_saat:int=24):

    if df is None or df.empty:
        return False
    
    son_cekim= pd.to_datetime(df['cekildigi_zaman']).max()
    fark = datetime.now()- son_cekim

    return fark.total_seconds() / 3600 < max_saat

tablo_olustur()