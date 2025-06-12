import streamlit as st
import pandas as pd
import numpy as np

# ------------------------------------------------------------------
# Configuração da página
# ------------------------------------------------------------------
st.set_page_config(page_title="Supplier Performance Dashboard", page_icon="📦", layout="wide")
st.title("📦 Supplier Performance Dashboard")

# ------------------------------------------------------------------
# Upload do arquivo
# ------------------------------------------------------------------
st.sidebar.header("📁 Carregar dados")
uploaded_file = st.sidebar.file_uploader(
    "Selecione a planilha (.xlsx ou .csv)", type=["xlsx", "csv"]
)

# ------------------------------------------------------------------
# Função de leitura robusta
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(file):
    try:
        # 1) Lê sem assumir cabeçalho fixo
        if file.name.endswith(".csv"):
            df = pd.read_csv(file, header=None, dtype=str)
        else:
            df = pd.read_excel(file, header=None)
        
        # 2) Procura nas primeiras 5 linhas a que contém "Vendor"
        header_row = None
        for i in range(min(5, len(df))):
            if df.iloc[i].astype(str).str.contains("Vendor", case=False).any():
                header_row = i
                break
        
        if header_row is None:
            st.error("Coluna 'Vendor' não encontrada no arquivo.")
            st.stop()
        
        # 3) Define cabeçalho
        df.columns = df.iloc[header_row].astype(str).str.strip()
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        
        # 4) Renomeia/normaliza
        rename_map = {
            "vendor name": "Vendor", "vendor": "Vendor",
            "vendor no.": "Vendor No", "order no.": "Order",
            "item no.": "Item No", "item description": "Item",
            "item cost": "Item Cost", "quantity": "Quantity",
            "cost per order": "Cost per order", "a/p terms": "AP Terms",
            "order date": "Order Date", "arrival date": "Arrival Date",
        }
        
        # Normaliza nomes das colunas
        df.columns = [str(c).strip() for c in df.columns]
        df = df.rename(columns=lambda x: rename_map.get(x.lower(), x))
        
        # Remove linhas completamente vazias
        df = df.dropna(how='all')
        
        # 5) Converte tipos numéricos
        for col in ["Item Cost", "Quantity", "Cost per order", "AP Terms"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 6) Calcula Lead-time
        if {"Order Date", "Arrival Date"}.issubset(df.columns):
            df["Order Date"] = pd.to_datetime(df["Order Date"], errors="coerce")
            df["Arrival Date"] = pd.to_datetime(df["Arrival Date"], errors="coerce")
            df["Lead Time"] = (df["Arrival Date"] - df["Order Date"]).dt.days
            
            # Remove valores negativos de lead time
            df.loc[df["Lead Time"] < 0, "Lead Time"] = np.nan
        
        return df
    
    except Exception as e:
        st.error(f"Erro ao carregar arquivo: {str(e)}")
        st.stop()

# ------------------------------------------------------------------
# Helpers para Composite Score
# ------------------------------------------------------------------
def add_composite(df_metrics):
    """Adiciona coluna Composite_Score ao DataFrame (lead, cost, AP)."""
    df = df_metrics.copy()
    
    # Verifica se há dados suficientes
    if len(df) == 0:
        df["Composite_Score"] = 0
        return df
    
    # Normalização (0-1) com tratamento de divisão por zero
    for col, new_col in [
        ("Avg_Lead_Days", "Norm_Lead"),
        ("Avg_Item_Cost", "Norm_Cost"),
        ("Avg_AP_Terms", "Norm_AP")
    ]:
        if col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            if max_val > min_val:
                df[new_col] = (df[col] - min_val) / (max_val - min_val)
            else:
                df[new_col] = 0
        else:
            df[new_col] = 0
    
    # Composite Score (quanto menor Lead e Cost → melhor, quanto maior AP → melhor)
    df["Composite_Score"] = (1 - df["Norm_Lead"]) * 0.4 + (1 - df["Norm_Cost"]) * 0.4 + df["Norm_AP"] * 0.2
    
    return df

# ------------------------------------------------------------------
# Se um arquivo foi enviado
# ------------------------------------------------------------------
if uploaded_file:
    df_raw = load_data(uploaded_file)
    
    # Verifica se há dados válidos
    if len(df_raw) == 0:
        st.error("O arquivo não contém dados válidos.")
        st.stop()
    
    # ------------------ Filtros gerais ----------------------------
    st.sidebar.header("🔧 Filtros gerais")
    
    # Filtro de fornecedores
    suppliers = sorted(df_raw["Vendor"].dropna().unique())
    if len(suppliers) == 0:
        st.error("Nenhum fornecedor encontrado nos dados.")
        st.stop()
    
    sel_suppliers = st.sidebar.multiselect("Fornecedores", suppliers, default=suppliers[:5] if len(suppliers) > 5 else suppliers)
    
    # Função helper para sliders
    def slide_range(col, label, key):
        if col not in df_raw.columns:
            return None, None
        
        values = df_raw[col].dropna()
        if len(values) == 0:
            return None, None
            
        mi, ma = float(values.min()), float(values.max())
        if mi == ma:
            return mi, ma
        
        return st.sidebar.slider(label, mi, ma, (mi, ma), key=key)
    
    # Sliders para filtros
    lt_min, lt_max = slide_range("Lead Time", "Lead Time (dias)", "lt")
    ap_min, ap_max = slide_range("AP Terms", "Prazo A/P (dias)", "ap")
    cost_min, cost_max = slide_range("Item Cost", "Custo unitário", "cost")
    
    # Aplica filtros
    df_filtered = df_raw[df_raw["Vendor"].isin(sel_suppliers)].copy()
    
    if lt_min is not None and "Lead Time" in df_filtered.columns:
        df_filtered = df_filtered[(df_filtered["Lead Time"] >= lt_min) & (df_filtered["Lead Time"] <= lt_max)]
    
    if ap_min is not None and "AP Terms" in df_filtered.columns:
        df_filtered = df_filtered[(df_filtered["AP Terms"] >= ap_min) & (df_filtered["AP Terms"] <= ap_max)]
    
    if cost_min is not None and "Item Cost" in df_filtered.columns:
        df_filtered = df_filtered[(df_filtered["Item Cost"] >= cost_min) & (df_filtered["Item Cost"] <= cost_max)]
    
    # Verifica se há dados após filtros
    if len(df_filtered) == 0:
        st.warning("Nenhum dado encontrado com os filtros selecionados.")
        st.stop()
    
    # ------------------ Filtro por produto -----------------------
    st.sidebar.header("📦 Produto específico (opcional)")
    item_col = "Item" if "Item" in df_filtered.columns else "Item No" if "Item No" in df_filtered.columns else None
    
    if item_col:
        items = sorted(df_filtered[item_col].dropna().unique())
        sel_item = st.sidebar.selectbox("Selecione um produto", ["Todos"] + list(items))
    else:
        sel_item = "Todos"
        st.sidebar.info("Coluna de produtos não encontrada")
    
    # ----------- SEÇÃO 1: produto escolhido ----------------------
    if sel_item != "Todos" and item_col:
        df_product = df_filtered[df_filtered[item_col] == sel_item].copy()
        
        if len(df_product) > 0:
            st.subheader(f"🔎 Detalhes do produto: *{sel_item}*")
            
            # Agregações com tratamento de colunas ausentes
            agg_dict = {"Order": "count"}
            if "Lead Time" in df_product.columns:
                agg_dict["Lead Time"] = "mean"
            if "AP Terms" in df_product.columns:
                agg_dict["AP Terms"] = "mean"
            if "Item Cost" in df_product.columns:
                agg_dict["Item Cost"] = "mean"
            if "Cost per order" in df_product.columns:
                agg_dict["Cost per order"] = "sum"
            
            prod_metrics = df_product.groupby("Vendor").agg(agg_dict).reset_index()
            
            # Renomeia colunas
            rename_dict = {
                "Order": "Orders",
                "Lead Time": "Avg_Lead_Days",
                "AP Terms": "Avg_AP_Terms",
                "Item Cost": "Avg_Item_Cost",
                "Cost per order": "Total_Spend"
            }
            prod_metrics = prod_metrics.rename(columns=rename_dict)
            
            # Adiciona colunas ausentes com valores padrão
            for col in ["Avg_Lead_Days", "Avg_AP_Terms", "Avg_Item_Cost"]:
                if col not in prod_metrics.columns:
                    prod_metrics[col] = 0
            
            prod_metrics = add_composite(prod_metrics).sort_values("Composite_Score", ascending=False)
            
            if len(prod_metrics) > 0:
                best_vendor = prod_metrics.iloc[0]["Vendor"]
                st.success(f"🏆 Melhor fornecedor para *{sel_item}*: **{best_vendor}**")
                
                # Formatação condicional
                format_dict = {}
                if "Avg_Lead_Days" in prod_metrics.columns:
                    format_dict["Avg_Lead_Days"] = "{:.1f}"
                if "Avg_AP_Terms" in prod_metrics.columns:
                    format_dict["Avg_AP_Terms"] = "{:.0f}"
                if "Avg_Item_Cost" in prod_metrics.columns:
                    format_dict["Avg_Item_Cost"] = "{:.2f}"
                if "Total_Spend" in prod_metrics.columns:
                    format_dict["Total_Spend"] = "{:.0f}"
                format_dict["Composite_Score"] = "{:.3f}"
                
                st.dataframe(
                    prod_metrics.style.format(format_dict),
                    use_container_width=True
                )
                
                st.bar_chart(prod_metrics.set_index("Vendor")["Composite_Score"])
                
                with st.expander("📄 Ver transações deste produto"):
                    st.dataframe(df_product, use_container_width=True)
        else:
            st.info(f"Nenhuma transação encontrada para o produto {sel_item}")
    
    # ----------- SEÇÃO 2: visão geral por fornecedor -------------
    st.subheader("📊 Resumo geral por fornecedor (todos os produtos filtrados)")
    
    # Agregações com tratamento de colunas ausentes
    agg_dict = {"Order": "count"}
    if "Lead Time" in df_filtered.columns:
        agg_dict["Lead Time"] = "mean"
    if "AP Terms" in df_filtered.columns:
        agg_dict["AP Terms"] = "mean"
    if "Item Cost" in df_filtered.columns:
        agg_dict["Item Cost"] = "mean"
    if "Cost per order" in df_filtered.columns:
        agg_dict["Cost per order"] = "sum"
    
    metrics = df_filtered.groupby("Vendor").agg(agg_dict).reset_index()
    
    # Renomeia colunas
    rename_dict = {
        "Order": "Orders",
        "Lead Time": "Avg_Lead_Days",
        "AP Terms": "Avg_AP_Terms",
        "Item Cost": "Avg_Item_Cost",
        "Cost per order": "Total_Spend"
    }
    metrics = metrics.rename(columns=rename_dict)
    
    # Adiciona colunas ausentes com valores padrão
    for col in ["Avg_Lead_Days", "Avg_AP_Terms", "Avg_Item_Cost"]:
        if col not in metrics.columns:
            metrics[col] = 0
    
    metrics = add_composite(metrics)
    
    # Ordenação
    st.sidebar.header("📈 Ordenação")
    valid_cols = [col for col in metrics.columns if col != "Vendor"]
    default_idx = valid_cols.index("Composite_Score") if "Composite_Score" in valid_cols else 0
    sort_col = st.sidebar.selectbox("Ordenar por", valid_cols, index=default_idx)
    asc = st.sidebar.checkbox("Crescente", value=False)
    
    # Formatação condicional
    format_dict = {}
    if "Avg_Lead_Days" in metrics.columns:
        format_dict["Avg_Lead_Days"] = "{:.1f}"
    if "Avg_AP_Terms" in metrics.columns:
        format_dict["Avg_AP_Terms"] = "{:.0f}"
    if "Avg_Item_Cost" in metrics.columns:
        format_dict["Avg_Item_Cost"] = "{:.2f}"
    if "Total_Spend" in metrics.columns:
        format_dict["Total_Spend"] = "{:.0f}"
    format_dict["Composite_Score"] = "{:.3f}"
    
    st.dataframe(
        metrics.sort_values(sort_col, ascending=asc).style.format(format_dict),
        use_container_width=True
    )
    
    # Gráficos
    c1, c2 = st.columns(2)
    if "Total_Spend" in metrics.columns:
        c1.subheader("💰 Gasto Total por Fornecedor")
        c1.bar_chart(metrics.set_index("Vendor")["Total_Spend"])
    
    if "Avg_Lead_Days" in metrics.columns:
        c2.subheader("⏱️ Lead Time Médio por Fornecedor")
        c2.bar_chart(metrics.set_index("Vendor")["Avg_Lead_Days"])
    
    # ----------- SEÇÃO 3: "placar de vitórias" -------------------
    if item_col and "Lead Time" in df_filtered.columns:
        st.subheader("🏅 Quantas vezes cada fornecedor é o melhor para um produto?")
        
        wins = {}
        for itm in df_filtered[item_col].dropna().unique():
            grp = df_filtered[df_filtered[item_col] == itm]
            
            agg_dict = {}
            if "Lead Time" in grp.columns:
                agg_dict["Lead Time"] = "mean"
            if "AP Terms" in grp.columns:
                agg_dict["AP Terms"] = "mean"
            if "Item Cost" in grp.columns:
                agg_dict["Item Cost"] = "mean"
            
            if agg_dict:
                m = grp.groupby("Vendor").agg(agg_dict).reset_index()
                
                # Renomeia colunas
                rename_dict = {
                    "Lead Time": "Avg_Lead_Days",
                    "AP Terms": "Avg_AP_Terms",
                    "Item Cost": "Avg_Item_Cost"
                }
                m = m.rename(columns=rename_dict)
                
                # Adiciona colunas ausentes
                for col in ["Avg_Lead_Days", "Avg_AP_Terms", "Avg_Item_Cost"]:
                    if col not in m.columns:
                        m[col] = 0
                
                m = add_composite(m)
                
                if len(m) > 0 and "Composite_Score" in m.columns:
                    winner = m.loc[m["Composite_Score"].idxmax(), "Vendor"]
                    wins[winner] = wins.get(winner, 0) + 1
        
        if wins:
            wins_df = pd.DataFrame({
                "Vendor": list(wins.keys()),
                "Wins": list(wins.values())
            }).sort_values("Wins", ascending=False)
            
            st.bar_chart(wins_df.set_index("Vendor")["Wins"])
    
    # Expander para ver dados brutos
    with st.expander("🔍 Ver todas as transações filtradas"):
        st.dataframe(df_filtered, use_container_width=True)

# ------------------------------------------------------------------
# Caso nenhum arquivo tenha sido enviado
# ------------------------------------------------------------------
else:
    st.info("👆 Faça upload da planilha para começar.", icon="📄")
    
    # Instruções de uso
    with st.expander("📖 Como usar este dashboard"):
        st.markdown("""
        ### Formato esperado do arquivo:
        
        O arquivo deve conter as seguintes colunas (não importa a ordem):
        - **Vendor**: Nome do fornecedor
        - **Order**: Número do pedido
        - **Item** ou **Item No**: Código/descrição do produto
        - **Item Cost**: Custo unitário
        - **Quantity**: Quantidade
        - **Cost per order**: Custo total do pedido
        - **AP Terms**: Prazo de pagamento (dias)
        - **Order Date**: Data do pedido
        - **Arrival Date**: Data de chegada
        
        ### Como o dashboard funciona:
        
        1. **Composite Score**: Pontuação composta que considera:
           - Lead Time (40%): Menor é melhor
           - Custo (40%): Menor é melhor
           - Prazo de pagamento (20%): Maior é melhor
        
        2. **Filtros**: Use os filtros laterais para analisar subconjuntos dos dados
        
        3. **Análise por produto**: Selecione um produto específico para ver qual fornecedor tem melhor desempenho
        """)
    
    # Exemplo de estrutura de dados
    with st.expander("📊 Exemplo de estrutura de dados"):
        example_data = pd.DataFrame({
            "Vendor": ["Fornecedor A", "Fornecedor B", "Fornecedor A"],
            "Order": ["PO-001", "PO-002", "PO-003"],
            "Item": ["Produto 1", "Produto 1", "Produto 2"],
            "Item Cost": [10.50, 9.75, 25.00],
            "Quantity": [100, 150, 50],
            "Cost per order": [1050.00, 1462.50, 1250.00],
            "AP Terms": [30, 45, 30],
            "Order Date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "Arrival Date": ["2024-01-15", "2024-01-20", "2024-01-18"]
        })
        st.dataframe(example_data)

# Footer
st.markdown("---")
st.markdown("📦 *Supplier Performance Dashboard v1.0*")