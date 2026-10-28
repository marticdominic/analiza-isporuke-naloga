import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# Konfiguracija stranice
st.set_page_config(
    page_title="Analiza radnih dana isporuke",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Analiza vremena isporuke naloga")
st.markdown("""
Ova aplikacija automatski analizira uvozne Excel tablice statusa naloga. 
Sustav automatski primjenjuje zadanu hijerarhiju za izračun radnih dana i sati (isključujući vikende):
1. **Odobrena isporuka** ➡️ **Isporučeno MMG**
2. Ako nema *Isporučeno MMG* ➡️ **Otpremljeno**
3. Ako nema niti to ➡️ **Spremno za otpremu**
""")

# Bočna traka za upload fajla
st.sidebar.header("📂 Učitavanje podataka")
uploaded_file = st.sidebar.file_uploader("Učitaj Excel datoteku (.xlsx)", type=["xlsx"])

def calculate_working_days_and_hours(start, end):
    if pd.isna(start) or pd.isna(end) or end < start:
        return 0, 0, 0.0
    
    d_start = start.normalize()
    d_end = end.normalize()
    
    # Izračun radnih dana (Ponedjeljak - Petak)
    bus_days = int(np.busday_count(d_start.strftime('%Y-%m-%d'), d_end.strftime('%Y-%m-%d')))
    
    # Ukupno sati
    total_seconds = (end - start).total_seconds()
    total_hours = total_seconds / 3600.0
    
    if d_start == d_end:
        hours = round(total_hours)
        return 0, hours, round(total_hours, 2)
        
    return max(0, bus_days), round(total_hours), round(total_hours, 2)

if uploaded_file is not None:
    try:
        # Učitavanje Excel tablice
        df = pd.read_excel(uploaded_file)
        
        # Provjera postojanja ključnih stupaca
        if 'Odobrena isporuka' not in df.columns:
            st.error("Greška: U učitanoj tablici ne postoji stupac 'Odobrena isporuka'!")
        else:
            with st.spinner("Obrada podataka u tijeku..."):
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
                
                # Izračun radnih dana i sati
                w_days, w_hours, tot_hours = [], [], []
                for idx, row in df_analysis.iterrows():
                    d, h, th = calculate_working_days_and_hours(row['Odobrena isporuka'], row['Vrijeme završetka'])
                    w_days.append(d)
                    w_hours.append(h)
                    tot_hours.append(th)
                
                df_analysis['Radni dani'] = w_days
                df_analysis['Sati (zaokruženi)'] = w_hours
                df_analysis['Ukupno sati (decimalno)'] = tot_hours
                
                # Filtriranje važećih
                df_valid = df_analysis.dropna(subset=['Odobrena isporuka']).copy()
                
            st.success( erfolgreich = f"Uspješno obrađeno {len(df_valid):,} naloga!")
            
            # Prikaz metrika u karticama
            col1, col2, col3 = st.columns(3)
            col1.metric("Ukupno obrađenih naloga", f"{len(df_valid):,}")
            col2.metric("Prosjek radnih dana", f"{df_valid['Radni dani'].mean():.2f}")
            col3.metric("Medijan radnih dana", f"{df_valid['Radni dani'].median():.0f}")
            
            # Pregled po statusima
            st.subheader("📊 Sažetak po korištenim statusima završetka")
            summary_status = df_valid.groupby('Završni status (izvor)').agg(
                Broj_naloga=('Broj naloga', 'count'),
                Prosjek_radnih_dana=('Radni dani', 'mean'),
                Medijan_radnih_dana=('Radni dani', 'median'),
                Prosjek_sati=('Sati (zaokruženi)', 'mean')
            ).reset_index()
            st.dataframe(summary_status, use_container_width=True)
            
            # Pregled po skladištima ako stupac postoji
            if 'Skladište' in df_valid.columns:
                st.subheader("🏢 Sažetak po skladištima")
                summary_wh = df_valid.groupby('Skladište').agg(
                    Broj_naloga=('Broj naloga', 'count'),
                    Prosjek_radnih_dana=('Radni dani', 'mean'),
                    Prosjek_sati=('Sati (zaokruženi)', 'mean')
                ).reset_index()
                st.dataframe(summary_wh, use_container_width=True)
            
            # Prikaz tablice sa svim podacima
            st.subheader("🔍 Detaljni pregled izračuna (uzorci)")
            st.dataframe(df_valid[['Broj naloga', 'Skladište', 'Naziv partnera', 'Odobrena isporuka', 'Završni status (izvor)', 'Vrijeme završetka', 'Radni dani', 'Sati (zaokruženi)']].head(100), use_container_width=True)
            
            # Export u Excel gumb
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_valid.to_excel(writer, sheet_name='Analiza Naloga', index=False)
                summary_status.to_excel(writer, sheet_name='Pregled po Statusima', index=False)
                if 'Skladište' in df_valid.columns:
                    summary_wh.to_excel(writer, sheet_name='Pregled po Skladištima', index=False)
            processed_data = output.getvalue()
            
            st.sidebar.markdown("---")
            st.sidebar.download_button(
                label="📥 Preuzmi obrađeni Excel",
                data=processed_data,
                file_name="Analiza_vremena_isporuke_rezultat.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Došlo je do greške prilikom čitanja datoteke: {e}")
else:
    st.info("👈 Molimo učitajte Excel datoteku putem izbornika s lijeve strane kako biste pokrenuli analizu.")
