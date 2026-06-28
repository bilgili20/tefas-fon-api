from fastapi import FastAPI,HTTPException
from pytefas import Crawler
from datetime import datetime,timedelta
from dotenv import load_dotenv
from groq import Groq

import database
import os

app =FastAPI(title ='Tefas Fon API')

tefas =Crawler()
load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))



@app.get('/')
def root():
    return{'mesaj':"Tefas Fon API'sine hoşgeldiniz."}

@app.get("/saglik")
def saglik():
    return{"durum":"calisiyor"}

@app.get("/fon/{kod}")
def fon_getir(kod:str, gun: int=30):

    try:

        cache_df = database.cache_oku(kod,gun)

        if database.cache_guncel(cache_df):
            print(f"Cache'den geliyor:{kod}")
            return {
                "fon_kodu":kod.upper(),
                "kaynak" :"cache",
                "kayit_sayisi": len(cache_df),
                "veri":cache_df[["tarih","fiyat"]].to_dict(orient="records")
            }

        print("Tefas'tan çekiliyor:{kod}")



        bitis = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now()-timedelta(days=gun)).strftime("%Y-%m-%d")

        df = tefas.fetch(
            start =baslangic,
            end=bitis,
            kind='YAT',
            fund_code=kod
        )

        if df.empty:
            raise HTTPException(status_code=404,detail=f'{kod} kodlu fon bulunamadı.')
        
        database.kaydet(kod,df)

        return {
            "fon_kodu":kod.upper(),
            "baslangic_tarihi":baslangic,
            "bitis_tarihi":bitis,
            "kayit_sayisi":len(df),
            "veri":df[["date","price"]].to_dict(orient='records')


        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Veri çekme hatası:{str(e)}')

@app.get("/karsilastir")
def fonlari_karsilastir(kodlar:str,gun: int = 30):

    #kodlar: virgülle ayrılmış olacak
    try:
        fon_listesi = [k.strip().upper() for k in kodlar.split(",")]

        if len(fon_listesi) <2 :
            raise HTTPException(
                status_code=400,
                detail='En az 2 fon kodu giriniz'
        )
        bitis = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now()-timedelta(days=gun)).strftime("%Y-%m-%d")

        sonuclar = []

        for kod in fon_listesi:
            try:

                cache_df = database.cache_oku(kod,gun)
                if database.cache_guncel(cache_df):
                    print(f'Cache: {kod}')

                    df= cache_df.rename(columns={'tarih':'date','fiyat':'price'})
                else:

                    df= tefas.fetch(
                        start=baslangic,
                        end=bitis,
                        kind='YAT',
                        fund_code=kod
                    )
                    if df.empty:
                        sonuclar.append({
                            'fon_kodu':kod,
                            'durum':'veri bulunamadı'
                        })
                        continue
                    database.kaydet(kod,df)

                    
                df = df.sort_values('date')
                ilk= df['price'].iloc[0]
                son=df['price'].iloc[-1]

                getiri = ((son-ilk)/ilk)*100
                volatilite = df['price'].pct_change().std()*100

                risk_getiri_orani = getiri/volatilite if volatilite > 0 else 0

                sonuclar.append({
                    'fon_kodu':kod,
                    'durum':'ok',
                    'getiri_yuzde':round(getiri,2),
                    'volatilite_yuzde':round(volatilite,2),
                    'risk_getiri_orani': round(risk_getiri_orani,2)

                })
            except Exception as e:
                
                sonuclar.append({
                    'fon_kodu':kod,
                    'durum':f'hata:{str(e)}'
                 })
        basarili =[ s for s in sonuclar if s['durum']=='ok']
        basarili.sort(key=lambda x : x['getiri_yuzde'], reverse=True)

        return {
            'gun_sayisi':gun,
            'toplam_fon':len(fon_listesi),
            'siralama':basarili,
            'tum_sonuclar':sonuclar,
        }
    except HTTPException:
        raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=f'Karşılaştırma hatası: {str(e)}')
@app.get('/fon/{kod}/buyukluk')
def fon_buyuklugu(kod:str): 

        bitis = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d")

        df = tefas.fetch(start=baslangic,end=bitis,kind='YAT',fund_code=kod)
        if df is None or df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"{kod} kodlu fon için veri bulunamadı"
            )
        print('çalıştı')
        son_satir=df.iloc[-1]
    
        portfolio_size =float(son_satir.get('portfolio_size',0))
        investor_count = float(son_satir.get('investor_count',0))

        ortalama_yatirim = portfolio_size / investor_count if investor_count > 0 else 0

        return {
            'fon_kodu': kod.upper(),
            'portfolio_size_tl':portfolio_size,
            'investor_count': investor_count,
            'ortalama_yatirim_tl': round(ortalama_yatirim,2),
            'profil':'kurumsal' if ortalama_yatirim > 100000 else 'bireysel'
        }

@app.get('/fon/{kod}/yorum')
def fon_ai_yorum(kod:str,gun:int=30):
    try:
        
        bitis = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now()-timedelta(days=gun)).strftime("%Y-%m-%d")
        df= tefas.fetch(start=baslangic,end=bitis,fund_code=kod,kind='YAT')
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"{kod} bulunamadı")
        
        df=df.sort_values('date')
        ilk= float(df['price'].iloc[0])
        son = float(df['price'].iloc[-1])
        getiri = ((son-ilk)/ilk)*100
        volatilite = float(df['price'].pct_change().std()*100)
        portfolio_size_tl =float(df['portfolio_size'].iloc[-1])
        investor_count= float(df['investor_count'].iloc[-1])


        prompt = f"""
            Aşağıdaki Türk yatırım fonu verisini analiz et ve 3-4 cümlelik Türkçe yorum yaz.

        Fon: {kod.upper()}
        Dönem: Son {gun} gün
        Getiri: %{getiri:.2f}
        Volatilite: %{volatilite:.2f}
   
        Yatırımcı Sayısı:{investor_count},
        Portfolyo Büyüklüğü:{portfolio_size_tl},

        Bu verilere dayanarak 5-6 cümlelik Türkçe yorum yap.
        Performansı ve risk seviyesini değerlendir.
        Yatırım tavsiyesi VERME.

        ÖNEMLİ: Yorumunda placeholder kullanma. Sadece yukarıdaki gerçek değerlerden bahset."""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Sen finansal analiz uzmanısın."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        yorum=response.choices[0].message.content

        return{
            'fon_kodu':kod.upper(),
            'metrikler':{
            'getiri_yuzde': round(getiri,2),
            'volatilite_yuzde': round(volatilite,2),
            'yatirimci_sayisi':investor_count,
            'portfolio_buyuklugu':portfolio_size_tl
            },
            'ai_yorumu':yorum
        }
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))

@app.get('/fon/{kod}/getiri-hesapla')
def getiri_hesaplama(kod:str,anapara:float,gun:int=30):
    try:
        cache_df = database.cache_oku(kod, gun)
        
        if database.cache_guncel(cache_df):
            df = cache_df.rename(columns={"tarih": "date", "fiyat": "price"})
        else:
            bitis = datetime.now().strftime("%Y-%m-%d")
            baslangic = (datetime.now()-timedelta(days=gun)).strftime("%Y-%m-%d")
            df=tefas.fetch(start=baslangic,end=bitis,fund_code=kod,kind='YAT')

            if df is None or df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"{kod} kodlu fon bulunamadı"
                )
            
            database.kaydet(kod, df)

        df=df.sort_values('date')

        ilk= float(df['price'].iloc[0])
        son = float(df['price'].iloc[-1])

        degisim = (son-ilk)/ilk
        yuzde= degisim*100
        final_anapara = anapara*(1+degisim)
        anapara_degisim = final_anapara- anapara

        return{
            'fon_kodu':kod.upper(),
            'baslangic_anapara':anapara,
            'final_anapara':round(final_anapara,2),
            'degisim': round(anapara_degisim,2),
            'yuzde_degisim': round(yuzde,2),
            'kazanc_mi': anapara_degisim>0

        }
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))