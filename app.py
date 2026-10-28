import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# Konfiguracija stranice i vizualnog stila
st.set_page_config(
    page_title="Analiza radnih dana i sati isporuke",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Analiza vremena i radnih dana isporuke naloga")
st.markdown("""
Ova aplikacija automatski analizira uvozne tablice statusa naloga i računa **radne dane i radne sate** (isključujući vikende i noćne sate) od **Odobrene isporuke** do završnog statusa po hijerarhiji:
1. **Isporučeno MMG**
2. Ako nema *Isporučeno MMG* ➡️ **Otpremljeno**
3. Ako nema niti to ➡️ **Spremno za otpremu**
""")

# Bočna traka za upload fajla
st.sidebar.header("📂 Upravljanje podacima")
uploaded_file = st.sidebar.file_uploader("Učitaj Excel datoteku (.xlsx)", type=["xlsx"])

def calculate_working_days_and_net_hours(start, end):
    if pd.isna(start) or pd.isna(end) or end < start:
        return 0.0, 0.0
    
    d_start = start.normalize()
    d_end = end.normalize()
    
    # Izračun radnih dana (Ponedjeljak - Petak)
    bus_days = float(np.busday_count(d_start.strftime('%Y-%m-%d'), d_end.strftime('%Y-%m-%d')))
    
    # Izračun neto radnih sati (pretpostavljamo standardnu smjenu od 8h po radnom danu ili točni radni sati unutar radnih dana)
    # Da precizno izbacimo vikende i noći iz satnice:
    # Ako je unutar istog dana:
    if d_start == d_end:
        if start.weekday() >= 5: # Vikend
            return 0.0, 0.0
        # Ograničimo sate unutar radnog dana (npr. 08:00 do 16:00 ili čista razlika ako je unutar radnog vremena)
        diff_hours = (end - start).total_seconds() / 3600.0
        return 0.0, max(0.0, round(diff_hours, 2))
    
    # Za više dana: računamo punih 8 radnih sati po svakom radnom danu + parcijalni sati početnog i završnog dana
    # Elegantnije: koristimo numpy busday za sate (radni dani * 8 sati kao baza, plus precizno vrijeme)
    net_hours = bus_days * 24.0 # ili možemo precizno oduzeti vikende iz ukupnog vremena
    
    # Precizniji izračun: oduzimamo vikende iz ukupnog trajanja u sekundama
    total_seconds = (end - start).total_seconds()
    
    # Računamo vikend dane između start i end da ih oduzemo
    all_days = pd.date_range(d_start, d_end, freq='D')
    weekend_days = sum(1 for d in all_days if d.weekday() >= 5)
    
    # Oduzimamo vikende (po 24 sata)
    net_seconds = total_seconds - (weekend_days * 24 * 3600)
    net_hours_calculated = max(0.0, net_seconds / 3600.0)
    
    return max(0.0, bus_days), round(net_hours_calculated, 2)

def categorize_time(hours):
    dz_hours = hours / 8.0 if hours > 0 else 0
    if hours <= 10.0:
        return "1. Unutar 10 sati"
    elif hours <= 24.0:
        return "2. U roku od 24 sata (10-24h)"
    elif hours <= 48.0:
        return "3. Između 24 i 48 sati"
    else:
        return "4. Više od 48 sati"

if uploaded_file is not None:
    try:
        # Učitavanje Excel tablice
        df = pd.read_excel(uploaded_file)
        
        # Provjera postojanja ključnih stupaca
        if 'Odobrena isporuka' not in df.columns:
            st.error("Greška: U učitanoj tablici ne postoji stupac 'Odobrena isporuka'!")
        else:
            with st.spinner("Obrada i izračun radnih dana i sati u tijeku..."):
                df_analysis = df.copy()
                
                # Pretvorba u datume
                date_cols = ['Odobrena isporuka', 'Isporučeno MMG', 'Otpremljeno', 'Spremno za otpremu']
                for col in date_cols:
                    if col in df_analysis.columns:
                        df_analysis[col] = pd.to_datetime(df_analysis[col], errors='coerce')
                
                # Određivanje završnog statusa po hijerarhiji
                end_timestamps = []
                status_used = []
                
                for idx, row in df_analysis.iterrows():
                    start = row.get('Odobrena isporuka', pd.NaT)
                    if pd.isna(start):
                        end_timestamps.append(pd.NaT)
                        status_used.append('Nema odobrene isporuke')
                        continue
                        
                    if not pd.isna(row.get('Isporučeno MMG')):
                        end_timestamps.append(row['Isporučeno MMG'])
                        status_used.append('Isporučeno MMG')
                    elif not pd.isna(row.get('Otpremljeno')):
                        end_timestamps.append(row['Otpremljeno'])
                        status_used.append('Otpremljeno')
                    elif not pd.isna(row.get('Spremno za otpremu')):
                        end_timestamps.append(row['Spremno za otpremu'])
                        status_used.append('Spremno za otpremu')
                    else:
                        end_timestamps.append(pd.NaT)
                        status_used.append('Nema završnog statusa')
                
                df_analysis['Završni status (izvor)'] = status_used
                df_analysis['Vrijeme završetka'] = end_timestamps
                
                # Izračun radnih dana i radnih sati (bez vikenda)
                w_days, w_hours, time_cats = [], [], []
                for idx, row in df_analysis.iterrows():
                    d, h = calculate_working_days_and_net_hours(row['Odobrena isporuka'], row['Vrijeme završetka'])
                    w_days.append(round(d, 2))
                    w_hours.append(round(h, 2))
                    time_cats.append(categorize_time(h))
                
                df_analysis['Radni dani'] = w_days
                df_analysis['Radni sati'] = w_hours
                df_analysis['Vremenska kategorija'] = time_cats
                
                # Filtriranje važećih
                df_valid = df_analysis.dropna(subset=['Odobrena isporuka']).copy()
                
            st.success(f"Uspješno obrađeno {len(df_valid):,} naloga!")
            
            # --- KPI KARTICE ---
            st.markdown("### 📌 Ključni pokazatelji (KPI)")
            kpi1, kpi2, kpi3 = st.columns(3)
            with kpi1:
                st.metric("Ukupno obrađenih naloga", f"{len(df_valid):,}")
            with kpi2:
                st.metric("Prosjek radnih dana", f"{df_valid['Radni dani'].mean():.2f}")
            with kpi3:
                st.metric("Prosjek radnih sati", f"{df_valid['Radni sati'].mean():.2f} h")
            
            st.markdown("---")
            
            # --- IZVJEŠTAJ PO VREMENSKIM KATEGORIJAMA ---
            st.subheader("⏱️ Izvještaj po vremenskim intervalima (radni sati)")
            cat_counts = df_valid['Vremenska kategorija'].value_counts().sort_index()
            cat_percentages = (cat_counts / len(df_valid) * 100).round(2)
            
            summary_time = pd.DataFrame({
                'Broj naloga': cat_counts,
                'Udio (%)': cat_percentages
            }).reset_index().rename(columns={'index': 'Vremenski interval'})
            
            st.dataframe(summary_time.style.format({'Broj naloga': '{:,}', 'Udio (%)': '{:.2f}%'}), use_container_width=True)
            
            # --- SAŽETAK PO STATUSIMA I SKLADIŠTIMA ---
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("📊 Pregled po statusima završetka")
                summary_status = df_valid.groupby('Završni status (izvor)').agg(
                    Broj_naloga=('Broj naloga', 'count'),
                    Prosjek_radnih_dana=('Radni dani', lambda x: round(x.mean(), 2)),
                    Prosjek_radnih_sati=('Radni sati', lambda x: round(x.mean(), 2))
                ).reset_index()
                st.dataframe(summary_status.style.format({'Broj naloga': '{:,}', 'Prosjek_radnih_dana': '{:.2f}', 'Prosjek_radnih_sati': '{:.2f}'}), use_container_width=True)
                
            with col_b:
                if 'Skladište' in df_valid.columns:
                    st.subheader("🏢 Pregled po skladištima")
                    summary_wh = df_valid.groupby('Skladište').agg(
                        Broj_naloga=('Broj naloga', 'count'),
                        Prosjek_radnih_dana=('Radni dani', lambda x: round(x.mean(), 2)),
                        Prosjek_radnih_sati=('Radni sati', lambda x: round(x.mean(), 2))
                    ).reset_index()
                    st.dataframe(summary_wh.style.format({'Broj naloga': '{:,}', 'Skladište': '{:.0f}', 'Prosjek_radnih_dana': '{:.2f}', 'Prosjek_radnih_sati': '{:.2f}'}), use_container_width=True)
            
            st.markdown("---")
            
            # --- DETALJNA TABLICA ---
            st.subheader("🔍 Detaljni pregled izračuna (uzorci naloga)")
            st.dataframe(df_valid[['Broj naloga', 'Skladište', 'Naziv partnera', 'Odobrena isporuka', 'Završni status (izvor)', 'Vrijeme završetka', 'Radni dani', 'Radni sati', 'Vremenska kategorija']].head(100), use_container_width=True)
            
            # --- EXPORT U EXCEL ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_valid.to_excel(writer, sheet_name='Analiza Naloga', index=False)
                summary_time.to_excel(writer, sheet_name='Vremenski Interval', index=False)
                summary_status.to_excel(writer, sheet_name='Pregled po Statusima', index=False)
                if 'Skladište' in df_valid.columns:
                    summary_wh.to_excel(writer, sheet_name='Pregled po Skladištima', index=False)
            processed_data = output.getvalue()
            
            st.sidebar.markdown("---")
            st.sidebar.download_button(
                label="📥 Preuzmi izvještaj radnih dana i sati",
                data=processed_data,
                file_name="Analiza_radnih_dana_i_sati.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Došlo je do greške prilikom čitanja datoteke: {e}")
else:
    st.info("👈 Molimo učitajte Excel datoteku putem bočnog izbornika s lijeve strane kako biste pokrenuli analizu radnih sati.")
