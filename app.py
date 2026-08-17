import datetime
import os
import re
from PIL import Image
import pandas as pd
import plotly.express as px
import psycopg2
import streamlit as st
from google import genai

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA DO STREAMLIT
# ==============================================================================
st.set_page_config(
    page_title="StudyQuest Pro — Modern Analytics",
    page_icon="⚡",
    layout="wide",
)

# Estilização do Menu Lateral
st.markdown(
    """
    <style>
        div.stRadio > div[role="radiogroup"] {
            gap: 14px !important;
        }
        div.stRadio [data-baseweb="radio"] div:first-child {
            background-color: #1e1e1e !important;
            border: 2px solid #00D26A !important;
        }
        div.stRadio label {
            padding: 6px 10px !important;
            border-radius: 8px;
            transition: background 0.2s ease;
        }
        div.stRadio label:hover {
            background-color: rgba(255, 255, 255, 0.07) !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ==============================================================================
# CONFIGURAÇÃO DA API DO GEMINI
# ==============================================================================
if "GEMINI_API_KEY" in st.secrets:
  os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

client = genai.Client()


# ==============================================================================
# BACKEND: GERENCIADOR DO SUPABASE (POSTGRESQL) E IA
# ==============================================================================
class DatabaseManager:

  def __init__(self):
    self.conn_str = st.secrets["supabase"]["connection_string"]

  def get_connection(self):
    return psycopg2.connect(self.conn_str)

  def resolver_questao_com_ia(self, enunciado, opcoes_dict):
    try:
      opcoes_formatadas = "\n".join(
          [f"{k}) {v}" for k, v in opcoes_dict.items() if v and v.strip()]
      )
      prompt = f"""
            Atue como um especialista em bancas de concursos públicos. 
            Analise a questão abaixo, aponte qual é a alternativa correta (A, B, C, D ou E) e forneça uma explicação fundamentada.

            Enunciado:
            {enunciado}

            Opções:
            {opcoes_formatadas}

            Responda obrigatoriamente no seguinte formato estrito:
            RESPOSTA: [Letra]
            EXPLICAÇÃO: [Sua explicação detalhada aqui]
            """
      response = client.models.generate_content(
          model="gemini-1.5-flash", contents=prompt, config={"temperature": 0.1}
      )
      return response.text
    except Exception as e:
      return f"Erro ao consultar a IA: {str(e)}"

  def processar_texto_localmente(self, texto_bruto):
    try:
      gab_match = re.search(
          r"(?:gabarito|resposta)[:\s]*([a-eA-E])", texto_bruto, re.IGNORECASE
      )
      gabarito = gab_match.group(1).upper() if gab_match else "A"

      alt_pattern = re.compile(
          r"(?:^|\n|\r|\s)([A-Ea-e])[\)\.\-]\s+", re.MULTILINE
      )
      matches = list(alt_pattern.finditer(texto_bruto))

      enunciado = texto_bruto
      op_a, op_b, op_c, op_d, op_e = "", "", "", "", ""

      if matches:
        enunciado = texto_bruto[: matches[0].start()].strip()
        alt_texts = {}

        for i in range(len(matches)):
          letra = matches[i].group(1).upper()
          inicio_conteudo = matches[i].end()
          fim_conteudo = (
              matches[i + 1].start()
              if i + 1 < len(matches)
              else len(texto_bruto)
          )
          alt_texts[letra] = texto_bruto[inicio_conteudo:fim_conteudo].strip()

        op_a = alt_texts.get("A", "")
        op_b = alt_texts.get("B", "")
        op_c = alt_texts.get("C", "")
        op_d = alt_texts.get("D", "")
        op_e = alt_texts.get("E", "")

        for letra, val in [
            ("A", op_a),
            ("B", op_b),
            ("C", op_c),
            ("D", op_d),
            ("E", op_e),
        ]:
          if val:
            val_limpo = re.sub(
                r"\n+\s*(?:gabarito|resposta)[:\s]*[A-E].*",
                "",
                val,
                flags=re.IGNORECASE,
            ).strip()
            if letra == "A":
              op_a = val_limpo
            elif letra == "B":
              op_b = val_limpo
            elif letra == "C":
              op_c = val_limpo
            elif letra == "D":
              op_d = val_limpo
            elif letra == "E":
              op_e = val_limpo

      return {
          "enunciado": enunciado,
          "op_a": op_a,
          "op_b": op_b,
          "op_c": op_c,
          "op_d": op_d,
          "op_e": op_e,
          "gabarito": gabarito,
          "explicacao": "",
      }
    except Exception as e:
      return {
          "enunciado": texto_bruto,
          "op_a": "",
          "op_b": "",
          "op_c": "",
          "op_d": "",
          "op_e": "",
          "gabarito": "A",
          "explicacao": "",
      }

  def ler_questao_por_imagem(self, image_path):
    try:
      imagem = Image.open(image_path)
      prompt = """
            Analise a imagem anexada, contendo uma questão de concurso.
            Transcreva e organize obrigatoriamente no formato:
            ENUNCIADO: [...]
            ALTERNATIVA_A: [...]
            ALTERNATIVA_B: [...]
            ALTERNATIVA_C: [...]
            ALTERNATIVA_D: [...]
            ALTERNATIVA_E: [...]
            GABARITO: [...]
            EXPLICACAO: [...]
            """
      response = client.models.generate_content(
          model="gemini-1.5-flash",
          contents=[prompt, imagem],
          config={"temperature": 0.1},
      )
      return response.text
    except Exception as e:
      return f"Erro ao processar imagem com IA: {str(e)}"

  def salvar_config_geral(self, perfil="Watson", chave="", valor=""):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO config_geral (perfil, chave, valor)
                VALUES (%s, %s, %s)
                ON CONFLICT (perfil, chave) DO UPDATE SET valor = EXCLUDED.valor
            """,
            (perfil, chave, valor),
        )
        conn.commit()
    st.cache_data.clear()

  def remover_config_geral(self, perfil="Watson", chave=""):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM config_geral WHERE perfil = %s AND chave = %s",
            (perfil, chave),
        )
        conn.commit()
    st.cache_data.clear()

  def obter_config_geral(self, perfil="Watson", chave="", default=""):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT valor FROM config_geral WHERE perfil = %s AND chave = %s",
            (perfil, chave),
        )
        res = cursor.fetchone()
        return res[0] if res else default

  def salvar_config_edital(
      self,
      perfil="Watson",
      concurso_nome="",
      materia="",
      qtd_questoes=10,
      peso=1.0,
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if materia.strip():
          cursor.execute(
              "DELETE FROM edital_config WHERE perfil = %s AND concurso_nome ="
              " %s AND (materia = '' OR materia ILIKE 'geral')",
              (perfil, concurso_nome.strip()),
          )
        cursor.execute(
            """
                INSERT INTO edital_config (perfil, concurso_nome, materia, qtd_questoes, peso)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (perfil, concurso_nome, materia) DO UPDATE SET
                    qtd_questoes = EXCLUDED.qtd_questoes,
                    peso = EXCLUDED.peso
            """,
            (
                perfil,
                concurso_nome.strip(),
                materia.strip(),
                int(qtd_questoes),
                float(peso),
            ),
        )
        conn.commit()
    st.cache_data.clear()

  def remover_materia_edital(
      self, perfil="Watson", concurso_nome="", materia=""
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM edital_config WHERE perfil = %s AND concurso_nome = %s"
            " AND materia = %s",
            (perfil, concurso_nome.strip(), materia.strip()),
        )
        cursor.execute(
            "SELECT id FROM questoes WHERE perfil = %s AND cargo = %s AND"
            " materia = %s",
            (perfil, concurso_nome.strip(), materia.strip()),
        )
        q_ids = [row[0] for row in cursor.fetchall()]
        for q_id in q_ids:
          cursor.execute(
              "DELETE FROM historico_respostas WHERE questao_id = %s", (q_id,)
          )
          cursor.execute("DELETE FROM questoes WHERE id = %s", (q_id,))

        cursor.execute(
            "SELECT COUNT(*) FROM edital_config WHERE perfil = %s AND"
            " concurso_nome = %s AND materia != ''",
            (perfil, concurso_nome.strip()),
        )
        restantes = cursor.fetchone()[0]
        if restantes == 0:
          cursor.execute(
              """
              INSERT INTO edital_config (perfil, concurso_nome, materia, qtd_questoes, peso)
              VALUES (%s, %s, '', 0, 1.0)
              ON CONFLICT (perfil, concurso_nome, materia) DO NOTHING
              """,
              (perfil, concurso_nome.strip()),
          )

        conn.commit()
    st.cache_data.clear()

  def deletar_concurso_inteiro(self, perfil="Watson", concurso_nome=""):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM edital_config WHERE perfil = %s AND concurso_nome ="
            " %s",
            (perfil, concurso_nome.strip()),
        )
        conn.commit()
    st.cache_data.clear()

  def obter_configs_edital(self, perfil="Watson", concurso_nome=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if concurso_nome and concurso_nome != "Todos" and concurso_nome.strip():
          cursor.execute(
              "SELECT materia, qtd_questoes, peso FROM edital_config WHERE"
              " perfil = %s AND concurso_nome = %s",
              (perfil, concurso_nome.strip()),
          )
        else:
          cursor.execute(
              "SELECT materia, qtd_questoes, peso FROM edital_config WHERE"
              " perfil = %s",
              (perfil,),
          )
        return {
            row[0]: {"qtd": row[1], "peso": row[2]}
            for row in cursor.fetchall()
            if row[0] and row[0].strip().lower() != "geral"
        }

  def obter_concursos_cadastrados(self, perfil="Watson"):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT concurso_nome FROM edital_config WHERE perfil = %s"
            " UNION SELECT DISTINCT cargo FROM questoes WHERE perfil = %s AND"
            " cargo IS NOT NULL AND cargo != ''",
            (perfil, perfil),
        )
        res = [row[0] for row in cursor.fetchall() if row[0]]
        return sorted(res)

  def registrar_resposta(self, questao_id, resposta_usuario):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT gabarito, total_erros, erros_consecutivos, total_tentativas 
                FROM questoes WHERE id = %s
            """,
            (questao_id,),
        )
        res = cursor.fetchone()
        if not res:
          return False, 0, 0

        gabarito, total_erros, erros_cons, total_tent = res
        total_erros = total_erros or 0
        erros_cons = erros_cons or 0
        total_tent = total_tent or 0

        acertou = (
            1
            if resposta_usuario.strip().upper() == gabarito.strip().upper()
            else 0
        )
        novo_total_tent = total_tent + 1

        if acertou:
          novo_erros_cons = 0
          novo_total_erros = total_erros
        else:
          novo_erros_cons = erros_cons + 1
          novo_total_erros = total_erros + 1

        cursor.execute(
            """
                UPDATE questoes 
                SET total_erros = %s, erros_consecutivos = %s, total_tentativas = %s
                WHERE id = %s
            """,
            (novo_total_erros, novo_erros_cons, novo_total_tent, questao_id),
        )
        cursor.execute(
            """
                INSERT INTO historico_respostas (questao_id, resposta_usuario, acertou)
                VALUES (%s, %s, %s)
            """,
            (questao_id, resposta_usuario.upper(), acertou),
        )
        conn.commit()
    st.cache_data.clear()
    return bool(acertou), novo_erros_cons, novo_total_erros

  def obter_questoes(
      self,
      perfil="Watson",
      cargo=None,
      materia=None,
      filtro_erros="Todos",
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        query = (
            "SELECT id, cargo, materia, enunciado, opcao_a, opcao_b, opcao_c,"
            " opcao_d, opcao_e, gabarito, explicacao, total_tentativas,"
            " total_erros, erros_consecutivos FROM questoes WHERE perfil = %s"
        )
        params = [perfil]
        if (
            cargo
            and cargo != "Todos"
            and cargo != "Cargo / Concurso"
            and cargo != "Nenhum cargo cadastrado"
        ):
          query += " AND cargo = %s"
          params.append(cargo)
        if materia and materia != "Todas":
          query += " AND materia = %s"
          params.append(materia)

        if filtro_erros == "Erros 1x":
          query += " AND erros_consecutivos = 1"
        elif filtro_erros == "Erros 2x":
          query += " AND erros_consecutivos = 2"
        elif filtro_erros == "Erros 3x+":
          query += " AND erros_consecutivos >= 3"

        query += " ORDER BY RANDOM()"
        cursor.execute(query, params)
        return cursor.fetchall()

  def obter_cargos(self, perfil="Watson"):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT cargo FROM questoes WHERE perfil = %s AND cargo IS"
            " NOT NULL AND cargo != '' ORDER BY cargo",
            (perfil,),
        )
        return [row[0] for row in cursor.fetchall()]

  def obter_cargos_totais(self, perfil="Watson"):
    cargos_set = set(self.obter_concursos_cadastrados(perfil))
    for c in self.obter_cargos(perfil):
      if c:
        cargos_set.add(c)
    return sorted(list(cargos_set))

  def obter_materias(self, perfil="Watson", cargo=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if cargo and cargo != "Todos" and cargo != "Cargo / Concurso":
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE perfil = %s AND"
              " cargo = %s AND materia IS NOT NULL AND materia != '' ORDER BY"
              " materia",
              (perfil, cargo),
          )
          materias_banco = [
              row[0]
              for row in cursor.fetchall()
              if row[0] and row[0].strip().lower() != "geral"
          ]
        else:
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE perfil = %s AND"
              " materia IS NOT NULL AND materia != '' ORDER BY materia",
              (perfil,),
          )
          materias_banco = [
              row[0]
              for row in cursor.fetchall()
              if row[0] and row[0].strip().lower() != "geral"
          ]

        configs = self.obter_configs_edital(perfil, cargo)
        materias_edital = [
            m for m in configs.keys() if m and m.strip().lower() != "geral"
        ]
        return sorted(list(set(materias_banco + materias_edital)))

  def adicionar_questao(
      self,
      perfil="Watson",
      cargo="",
      materia="",
      enunciado="",
      op_a="",
      op_b="",
      op_c="",
      op_d="",
      op_e="",
      gabarito="A",
      explicacao="",
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO questoes (perfil, cargo, materia, enunciado, opcao_a, opcao_b, opcao_c, opcao_d, opcao_e, gabarito, explicacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                perfil,
                cargo.strip(),
                materia.strip(),
                enunciado,
                op_a,
                op_b,
                op_c,
                op_d,
                op_e,
                gabarito.upper(),
                explicacao,
            ),
        )
        conn.commit()
    st.cache_data.clear()

  def deletar_questao(self, questao_id):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM historico_respostas WHERE questao_id = %s",
            (questao_id,),
        )
        cursor.execute("DELETE FROM questoes WHERE id = %s", (questao_id,))
        conn.commit()
    st.cache_data.clear()

  def obter_analise_dashboard(self, perfil="Watson", concurso_ativo=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if (
            concurso_ativo
            and concurso_ativo != "Todos"
            and concurso_ativo.strip()
        ):
          cursor.execute(
              "SELECT materia, qtd_questoes, peso, concurso_nome FROM"
              " edital_config WHERE perfil = %s AND concurso_nome = %s",
              (perfil, concurso_ativo.strip()),
          )
        else:
          cursor.execute(
              "SELECT materia, qtd_questoes, peso, concurso_nome FROM"
              " edital_config WHERE perfil = %s",
              (perfil,),
          )
        edital_rows = cursor.fetchall()
        edital_items = {}
        for row in edital_rows:
          mat, qtd, peso, conc = row
          if mat and mat.strip() and mat.strip().lower() != "geral":
            edital_items[(conc, mat)] = {"qtd": qtd, "peso": peso}

        if (
            concurso_ativo
            and concurso_ativo != "Todos"
            and concurso_ativo.strip()
        ):
          cursor.execute(
              "SELECT DISTINCT materia, COALESCE(NULLIF(cargo, ''), %s) FROM"
              " questoes WHERE perfil = %s AND cargo = %s AND materia IS NOT"
              " NULL",
              (concurso_ativo.strip(), perfil, concurso_ativo.strip()),
          )
        else:
          cursor.execute(
              "SELECT DISTINCT materia, COALESCE(NULLIF(cargo, ''), 'Geral')"
              " FROM questoes WHERE perfil = %s AND materia IS NOT NULL",
              (perfil,),
          )
        questoes_rows = cursor.fetchall()

        all_pairs = set(edital_items.keys())
        for mat, conc in questoes_rows:
          if mat and mat.strip() and mat.strip().lower() != "geral":
            all_pairs.add((conc, mat))

        detalhes_materias = []
        materia_mais_critica = "Nenhuma"
        max_pontos_perdidos = -1.0
        pontuacao_maxima_prova = 0.0
        pontuacao_projetada = 0.0
        total_erros_geral = 0
        total_tentativas_geral = 0

        if (
            concurso_ativo
            and concurso_ativo != "Todos"
            and concurso_ativo.strip()
        ):
          cursor.execute(
              "SELECT COUNT(id) FROM questoes WHERE perfil = %s AND cargo = %s"
              " AND explicacao IS NOT NULL AND TRIM(explicacao) != ''",
              (perfil, concurso_ativo.strip()),
          )
        else:
          cursor.execute(
              "SELECT COUNT(id) FROM questoes WHERE perfil = %s AND"
              " explicacao IS NOT NULL AND TRIM(explicacao) != ''",
              (perfil,),
          )
        total_comentadas = cursor.fetchone()[0] or 0

        for conc, mat in sorted(all_pairs, key=lambda x: (x[0], x[1])):
          cfg = edital_items.get((conc, mat), {"qtd": 0, "peso": 1.0})
          qtd_prova = cfg["qtd"]
          peso = cfg["peso"]

          cursor.execute(
              """
                  SELECT COUNT(id), SUM(total_tentativas), SUM(total_erros) 
                  FROM questoes WHERE perfil = %s AND (cargo = %s OR (%s = 'Geral' AND (cargo IS NULL OR cargo = ''))) AND materia = %s
              """,
              (perfil, conc, conc, mat),
          )
          q_cad, tent, erros = cursor.fetchone()
          q_cad = q_cad or 0
          tent = tent or 0
          erros = erros or 0
          acertos = tent - erros

          total_erros_geral += erros
          total_tentativas_geral += tent

          pontos_possiveis_mat = qtd_prova * peso
          pontuacao_maxima_prova += pontos_possiveis_mat

          if tent > 0:
            taxa_acerto = (acertos / tent) * 100.0
            pontos_estimados_mat = pontos_possiveis_mat * (taxa_acerto / 100.0)
            pontos_perdidos_mat = pontos_possiveis_mat - pontos_estimados_mat
          else:
            taxa_acerto = 0.0
            pontos_estimados_mat = 0.0
            pontos_perdidos_mat = 0.0

          pontuacao_projetada += pontos_estimados_mat

          if (
              tent > 0
              and pontos_perdidos_mat > max_pontos_perdidos
              and taxa_acerto < 100.0
          ):
            max_pontos_perdidos = pontos_perdidos_mat
            materia_mais_critica = f"{mat} ({conc})"

          detalhes_materias.append({
              "concurso_nome": conc,
              "materia": mat,
              "qtd_prova": qtd_prova,
              "peso": peso,
              "q_cadastradas": q_cad,
              "tentativas": tent,
              "certas": acertos,
              "erradas": erros,
              "taxa_acerto": taxa_acerto,
              "pontos_possiveis": pontos_possiveis_mat,
              "pontos_estimados": pontos_estimados_mat,
              "pontos_perdidos": pontos_perdidos_mat,
          })

        certas_geral = total_tentativas_geral - total_erros_geral
        taxa_global = (
            (certas_geral / total_tentativas_geral * 100.0)
            if total_tentativas_geral > 0
            else 0.0
        )

        return {
            "nome_concurso": concurso_ativo,
            "materias_detalhes": detalhes_materias,
            "materia_mais_critica": (
                materia_mais_critica if max_pontos_perdidos > 0 else "Nenhuma"
            ),
            "pontuacao_projetada": pontuacao_projetada,
            "pontuacao_maxima": pontuacao_maxima_prova,
            "total": total_tentativas_geral,
            "certas": certas_geral,
            "erradas": total_erros_geral,
            "comentadas": total_comentadas,
            "taxa_global": taxa_global,
        }


# Limpa qualquer cache anterior para evitar conflito de instâncias
st.cache_resource.clear()


@st.cache_resource
def get_db():
  return DatabaseManager()


db = get_db()


# --- FUNÇÕES CACHEADAS ---
@st.cache_data(ttl=60)
def cached_obter_analise_dashboard(perfil, concurso_ativo):
  return db.obter_analise_dashboard(perfil, concurso_ativo)


@st.cache_data(ttl=60)
def cached_obter_questoes(perfil, cargo, materia, filtro_erros):
  return db.obter_questoes(perfil, cargo, materia, filtro_erros)


@st.cache_data(ttl=300)
def cached_obter_cargos_totais(perfil):
  return db.obter_cargos_totais(perfil)


@st.cache_data(ttl=300)
def cached_obter_materias(perfil, cargo):
  return db.obter_materias(perfil, cargo)


# Inicialização do Session State
if "questoes_lista" not in st.session_state:
  st.session_state.questoes_lista = []
if "indice_atual" not in st.session_state:
  st.session_state.indice_atual = 0
if "resposta_enviada" not in st.session_state:
  st.session_state.resposta_enviada = False
if "resultado_atual" not in st.session_state:
  st.session_state.resultado_atual = None
if "concurso_selecionado" not in st.session_state:
  st.session_state.concurso_selecionado = "Geral (Todos)"

if "form_enunciado" not in st.session_state:
  st.session_state.form_enunciado = ""
if "form_op_a" not in st.session_state:
  st.session_state.form_op_a = ""
if "form_op_b" not in st.session_state:
  st.session_state.form_op_b = ""
if "form_op_c" not in st.session_state:
  st.session_state.form_op_c = ""
if "form_op_d" not in st.session_state:
  st.session_state.form_op_d = ""
if "form_op_e" not in st.session_state:
  st.session_state.form_op_e = ""
if "form_gabarito" not in st.session_state:
  st.session_state.form_gabarito = "A"
if "form_explicacao" not in st.session_state:
  st.session_state.form_explicacao = ""

# ==============================================================================
# FRONTEND: STREAMLIT APP UI
# ==============================================================================
st.sidebar.title("⚡ STUDYQUEST")

# --- SELETOR DE PERFIL (Watson, Laylla, Gabriel) ---
if "perfil_ativo" not in st.session_state:
  st.session_state.perfil_ativo = "Watson"

perfis_disponiveis = ["Watson", "Laylla", "Gabriel"]
perfil_escolhido = st.sidebar.selectbox(
    "👤 Perfil Ativo", perfis_disponiveis, key="selectbox_perfil"
)

if perfil_escolhido != st.session_state.perfil_ativo:
  st.session_state.perfil_ativo = perfil_escolhido
  st.session_state.questoes_lista = []
  st.session_state.indice_atual = 0
  st.session_state.resposta_enviada = False
  st.session_state.resultado_atual = None
  st.rerun()

st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "Navegação", ["📊 Dashboard", "📖 Questões", "➕ Cadastrar", "💾 Backup"]
)

perfil_atual = st.session_state.perfil_ativo

if menu == "📊 Dashboard":
  st.title(f"📊 Dashboard & Análise Estratégica ({perfil_atual})")

  cargos_cadastrados = db.obter_concursos_cadastrados(perfil_atual)
  opcoes_concurso = ["Geral (Todos)"] + cargos_cadastrados

  with st.container(border=True):
    st.subheader("🎯 Seleção e Gestão de Concursos")
    col_sel, col_novo, col_del = st.columns([3, 3, 2])

    with col_sel:
      current_idx = 0
      if st.session_state.concurso_selecionado in opcoes_concurso:
        current_idx = opcoes_concurso.index(
            st.session_state.concurso_selecionado
        )

      concurso_escolhido = st.selectbox(
          "Concurso Ativo", opcoes_concurso, index=current_idx
      )
      if concurso_escolhido != st.session_state.concurso_selecionado:
        st.session_state.concurso_selecionado = concurso_escolhido
        st.rerun()

    with col_novo:
      novo_concurso_input = st.text_input("Criar Novo Concurso")
      if st.button("➕ Adicionar Concurso"):
        if novo_concurso_input.strip():
          db.salvar_config_edital(
              perfil_atual, novo_concurso_input.strip(), "", 0, 1.0
          )
          st.session_state.concurso_selecionado = novo_concurso_input.strip()
          st.success(f"Concurso '{novo_concurso_input.strip()}' criado!")
          st.rerun()
        else:
          st.warning("Digite o nome do concurso!")

    with col_del:
      st.markdown("<br>", unsafe_allow_html=True)
      if (
          st.session_state.concurso_selecionado != "Geral (Todos)"
          and st.button("🗑️ Excluir Concurso Ativo", use_container_width=True)
      ):
        db.deletar_concurso_inteiro(
            perfil_atual, st.session_state.concurso_selecionado
        )
        st.success("Concurso excluído!")
        st.session_state.concurso_selecionado = "Geral (Todos)"
        st.rerun()

  ativo_param = (
      None
      if st.session_state.concurso_selecionado == "Geral (Todos)"
      else st.session_state.concurso_selecionado
  )
  dados = cached_obter_analise_dashboard(perfil_atual, ativo_param)

  total = dados.get("total", 0)
  certas = dados.get("certas", 0)
  erradas = dados.get("erradas", 0)
  taxa = dados.get("taxa_global", 0.0)
  comentadas = dados.get("comentadas", 0)

  st.markdown("### 📈 Visão Geral de Desempenho")
  col1, col2, col3, col4, col5 = st.columns(5)
  with col1:
    with st.container(border=True):
      st.metric("Total Resoluções", total, delta="Geral")
  with col2:
    with st.container(border=True):
      st.metric("Resoluções Certas", certas, delta="Acertos")
  with col3:
    with st.container(border=True):
      st.metric(
          "Resoluções Erradas", erradas, delta="Erros", delta_color="inverse"
      )
  with col4:
    with st.container(border=True):
      st.metric("Taxa de Acerto", f"{taxa:.2f}%")
  with col5:
    with st.container(border=True):
      st.metric("Comentadas", comentadas)

  st.markdown("<br>", unsafe_allow_html=True)

  c_info1, c_info2 = st.columns([3, 2])
  with c_info1:
    with st.container(border=True):
      st.markdown("##### 🥧 Peso e Pontos das Matérias no Concurso")
      if dados["materias_detalhes"]:
        df_mat = pd.DataFrame(dados["materias_detalhes"])
        fig = px.pie(
            df_mat,
            names="materia",
            values="pontos_possiveis",
            hole=0.4,
        )
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=240,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
      else:
        st.info("Nenhuma matéria cadastrada neste concurso para gerar o gráfico.")
  with c_info2:
    with st.container(border=True):
      st.metric("⚠️ PONTO CEGO (MAIOR DEFICIT)", dados["materia_mais_critica"])

  st.markdown("---")

  # --- FORMULÁRIO DE CADASTRO DE MATÉRIAS CORRIGIDO E SEMPRE DISPONÍVEL ---
  with st.container(border=True):
    st.subheader("⚙️ Cadastrar e Configurar Matérias no Edital")

    with st.form("form_edital_multi"):
      st.markdown("##### Adicionar / Atualizar Matéria")

      concursos_disponiveis_form = (
          cargos_cadastrados if cargos_cadastrados else ["Geral"]
      )
      default_conc_idx = 0
      if st.session_state.concurso_selecionado in concursos_disponiveis_form:
        default_conc_idx = concursos_disponiveis_form.index(
            st.session_state.concurso_selecionado
        )
      elif st.session_state.concurso_selecionado != "Geral (Todos)":
        concursos_disponiveis_form = [
            st.session_state.concurso_selecionado
        ] + concursos_disponiveis_form
        default_conc_idx = 0

      fc_conc, f1, f2, f3 = st.columns([2, 2, 1, 1])
      with fc_conc:
        concurso_alvo = st.selectbox(
            "Concurso Alvo",
            options=concursos_disponiveis_form,
            index=default_conc_idx,
        )
      with f1:
        mat_input = st.text_input("Nome da Matéria (ex: Direito Administrativo)")
      with f2:
        qtd_input = st.text_input("Qtd Questões na Prova", value="10")
      with f3:
        peso_input = st.text_input("Peso da Matéria", value="1.0")

      btn_salvar_edital = st.form_submit_button("+ Adicionar Matéria ao Edital")
      if btn_salvar_edital:
        if (
            concurso_alvo
            and mat_input.strip()
            and qtd_input.strip()
            and peso_input.strip()
        ):
          try:
            db.salvar_config_edital(
                perfil_atual,
                concurso_alvo.strip(),
                mat_input.strip(),
                int(qtd_input),
                float(peso_input),
            )
            st.success(
                f"Matéria '{mat_input.strip()}' adicionada ao edital de"
                f" '{concurso_alvo.strip()}'!"
            )
            st.rerun()
          except ValueError:
            st.error("Quantidade deve ser inteiro e Peso deve ser decimal.")
        else:
          st.warning("Preencha todos os campos e selecione o concurso alvo!")

  st.markdown("---")
  titulo_analise = (
      f"📋 Rendimento por Matéria — {st.session_state.concurso_selecionado}"
  )
  st.subheader(titulo_analise)

  if not dados["materias_detalhes"]:
    st.info(
        "Nenhuma matéria cadastrada neste concurso ainda. Adicione uma acima!"
    )
  else:
    for item in dados["materias_detalhes"]:
      with st.container(border=True):
        cols = st.columns([3, 1])
        with cols[0]:
          st.markdown(
              f"### 📚 {item['materia']} <span style='font-size: 0.8em; color:"
              f" gray;'>({item['concurso_nome']})</span>",
              unsafe_allow_html=True,
          )
          taxa_mat = item["taxa_acerto"]
          st.progress(
              int(taxa_mat) if taxa_mat <= 100 else 100,
              text=f"Taxa: {taxa_mat:.1f}%",
          )
          txt_stats = (
              f"**Acertos:** {item.get('certas', 0)} | **Erros:**"
              f" {item.get('erradas', 0)} | **Total Resolvidas:**"
              f" {item['tentativas']} | **Edital:** {item['qtd_prova']} q."
              f" (Peso {item['peso']:.1f})"
          )
          st.markdown(txt_stats)
        with cols[1]:
          st.markdown("<br>", unsafe_allow_html=True)
          if st.button(
              "🗑️ Excluir Matéria",
              key=f"del_mat_{item['concurso_nome']}_{item['materia']}",
          ):
            db.remover_materia_edital(
                perfil_atual, item["concurso_nome"], item["materia"]
            )
            st.rerun()

elif menu == "📖 Questões":
  st.title(f"📖 Resolução de Questões ({perfil_atual})")
  cargos = ["Todos"] + cached_obter_cargos_totais(perfil_atual)
  f_col1, f_col2, f_col3, f_col4 = st.columns([2, 2, 2, 2])
  with f_col1:
    cargo_filtro = st.selectbox("Cargo / Concurso", cargos)
  with f_col2:
    mats = ["Todas"] + cached_obter_materias(
        perfil_atual,
        cargo=cargo_filtro if cargo_filtro != "Todos" else None,
    )
    materia_filtro = st.selectbox("Matéria", mats)
  with f_col3:
    filtro_erros = st.selectbox(
        "Filtrar por Erros", ["Todos", "Erros 1x", "Erros 2x", "Erros 3x+"]
    )
  with f_col4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 Carregar Questões", use_container_width=True):
      st.session_state.questoes_lista = cached_obter_questoes(
          perfil_atual, cargo_filtro, materia_filtro, filtro_erros
      )
      st.session_state.indice_atual = 0
      st.session_state.resposta_enviada = False
      st.session_state.resultado_atual = None
      st.rerun()

  if st.session_state.questoes_lista:
    idx = st.session_state.indice_atual
    if idx < len(st.session_state.questoes_lista):
      q = st.session_state.questoes_lista[idx]
      (
          q_id,
          cargo_q,
          materia_q,
          enunciado,
          op_a,
          op_b,
          op_c,
          op_d,
          op_e,
          gabarito,
          explicacao,
          total_tentativas,
          total_erros,
          erros_cons,
      ) = q

      with st.container(border=True):
        st.markdown(
            f"**Cargo:** {cargo_q or 'Geral'} | **Matéria:** {materia_q} |"
            f" **Questão {idx + 1} de"
            f" {len(st.session_state.questoes_lista)}** | **Erros:**"
            f" {total_erros or 0}"
        )
        if erros_cons >= 3:
          st.error(
              f"🚨 ALERTA CRÍTICO: Você errou esta questão {erros_cons}x"
              " seguidas!"
          )
        elif erros_cons == 2:
          st.warning(
              "⚠️ ERRO RECORRENTE: Você errou esta questão nas últimas 2x!"
          )
        elif erros_cons == 1:
          st.info("ℹ️ Você errou esta questão na última tentativa (1x).")

        st.markdown("### Enunciado")
        st.info(enunciado)

        opcoes_dict = {"A": op_a, "B": op_b, "C": op_c, "D": op_d, "E": op_e}
        opcoes_validas = {k: v for k, v in opcoes_dict.items() if v and v.strip()}
        opcao_escolhida = st.radio(
            "Escolha a alternativa:",
            options=list(opcoes_validas.keys()),
            format_func=lambda x: f"{x}) {opcoes_validas[x]}",
            key=f"radio_resp_{q_id}",
        )

        col_acao1, col_acao2, col_acao3 = st.columns([2, 2, 2])
        with col_acao1:
          if st.button("✅ Confirmar Resposta"):
            acertou, novo_erros_cons, total_erros_reg = db.registrar_resposta(
                q_id, opcao_escolhida
            )
            st.session_state.resposta_enviada = True
            st.session_state.resultado_atual = {
                "acertou": acertou,
                "gabarito": gabarito,
                "explicacao": explicacao,
            }
            st.rerun()
        with col_acao2:
          if st.button("🤖 Resolver com IA"):
            resposta_ia = db.resolver_questao_com_ia(enunciado, opcoes_validas)
            st.session_state.resposta_enviada = True
            st.session_state.resultado_atual = {
                "acertou": None,
                "gabarito": gabarito,
                "explicacao": resposta_ia,
            }
            st.rerun()
        with col_acao3:
          if st.button("🗑️ Excluir Questão"):
            db.deletar_questao(q_id)
            st.success("Questão excluída!")
            st.session_state.questoes_lista.pop(idx)
            if (
                st.session_state.indice_atual
                >= len(st.session_state.questoes_lista)
                and st.session_state.indice_atual > 0
            ):
              st.session_state.indice_atual -= 1
            st.session_state.resposta_enviada = False
            st.rerun()

        if (
            st.session_state.resposta_enviada
            and st.session_state.resultado_atual
        ):
          res = st.session_state.resultado_atual
          if res["acertou"] is True:
            st.success("🎉 RESPOSTA CORRETA!")
            st.write(res["explicacao"] or "Sem explicação cadastrada.")
          elif res["acertou"] is False:
            st.error(f"❌ INCORRETA! Gabarito Oficial: ({res['gabarito']})")
            st.write(res["explicacao"] or "Sem explicação cadastrada.")
          else:
            st.info("🤖 Resposta da IA:")
            st.write(res["explicacao"])

          if st.button("Próxima Questão ➡️"):
            st.session_state.indice_atual += 1
            st.session_state.resposta_enviada = False
            st.session_state.resultado_atual = None
            st.rerun()
    else:
      st.info("Você concluiu todas as questões carregadas neste caderno!")
  else:
    st.info(
        "Utilize os filtros acima e clique em 'Carregar Questões' para iniciar."
    )

elif menu == "➕ Cadastrar":
  st.title(f"➕ Nova Questão & Automação Inteligente ({perfil_atual})")

  with st.expander("📝 Colar Texto Completo da Questão", expanded=True):
    texto_bruto_input = st.text_area(
        "Cole aqui o texto inteiro da questão:", height=150
    )

    if st.button(
        "⚡ Separar Automaticamente (Instantâneo / Sem Erros)",
        use_container_width=True,
    ):
      if texto_bruto_input.strip():
        dados_separados = db.processar_texto_localmente(texto_bruto_input)
        st.session_state.form_enunciado = dados_separados["enunciado"]
        st.session_state.form_op_a = dados_separados["op_a"]
        st.session_state.form_op_b = dados_separados["op_b"]
        st.session_state.form_op_c = dados_separados["op_c"]
        st.session_state.form_op_d = dados_separados["op_d"]
        st.session_state.form_op_e = dados_separados["op_e"]
        st.session_state.form_gabarito = dados_separados["gabarito"]
        st.session_state.form_explicacao = dados_separados["explicacao"]
        st.success("Texto separado com sucesso localmente!")
        st.rerun()
      else:
        st.warning("Cole o texto da questão primeiro!")

  with st.expander("🖼️ Leitura por Imagem (Print/Foto da Questão)"):
    imagem_file = st.file_uploader(
        "Selecione um arquivo de imagem", type=["png", "jpg", "jpeg", "webp"]
    )
    if imagem_file is not None and st.button("Processar Imagem com IA"):
      with open("temp_img.png", "wb") as f:
        f.write(imagem_file.getbuffer())
      resposta_ia = db.ler_questao_por_imagem("temp_img.png")
      if resposta_ia.startswith("Erro"):
        st.error(resposta_ia)
      else:
        texto_limpo_img = (
            resposta_ia.replace("**", "").replace("*", "").replace("`", "")
        )

        def extrair_tag_img(tag, texto):
          pattern = rf"(?:^|\n)\s*{tag}\s*:\s*(.*?)(?=\n\s*[A-Z_]{3,}\s*:|\Z)"
          match = re.search(pattern, texto, re.DOTALL | re.IGNORECASE)
          return match.group(1).strip() if match else ""

        st.session_state.form_enunciado = extrair_tag_img(
            "ENUNCIADO", texto_limpo_img
        )
        st.session_state.form_op_a = extrair_tag_img(
            "ALTERNATIVA_A", texto_limpo_img
        )
        st.session_state.form_op_b = extrair_tag_img(
            "ALTERNATIVA_B", texto_limpo_img
        )
        st.session_state.form_op_c = extrair_tag_img(
            "ALTERNATIVA_C", texto_limpo_img
        )
        st.session_state.form_op_d = extrair_tag_img(
            "ALTERNATIVA_D", texto_limpo_img
        )
        st.session_state.form_op_e = extrair_tag_img(
            "ALTERNATIVA_E", texto_limpo_img
        )
        gab_img = extrair_tag_img("GABARITO", texto_limpo_img).upper()
        if gab_img and gab_img[0] in ["A", "B", "C", "D", "E"]:
          st.session_state.form_gabarito = gab_img[0]
        st.session_state.form_explicacao = extrair_tag_img(
            "EXPLICACAO", texto_limpo_img
        )
        st.success("Imagem lida com sucesso!")
        st.rerun()

  cargos_iniciais = db.obter_cargos_totais(perfil_atual)
  if not cargos_iniciais:
    cargos_iniciais = ["Cargo / Concurso"]

  st.markdown("---")
  st.subheader("📝 Formulário de Revisão e Cadastro")
  cad_cargo = st.selectbox(
      "Cargo / Concurso", cargos_iniciais, key="cad_cargo_select"
  )
  materias_cargo = cached_obter_materias(perfil_atual, cargo=cad_cargo)
  if not materias_cargo:
    materias_cargo = ["Geral"]

  with st.form("form_cadastrar_questao"):
    cad_materia = st.selectbox("Matéria", options=materias_cargo)
    cad_enunciado = st.text_area(
        "Enunciado da Questão",
        value=st.session_state.form_enunciado,
        height=120,
    )

    c_op1, c_op2 = st.columns(2)
    with c_op1:
      op_a = st.text_input("Opção A", value=st.session_state.form_op_a)
      op_b = st.text_input("Opção B", value=st.session_state.form_op_b)
      op_c = st.text_input("Opção C", value=st.session_state.form_op_c)
    with c_op2:
      op_d = st.text_input("Opção D", value=st.session_state.form_op_d)
      op_e = st.text_input("Opção E", value=st.session_state.form_op_e)

    opcoes_gabarito_possiveis = ["A", "B", "C", "D", "E"]
    try:
      idx_gab = opcoes_gabarito_possiveis.index(st.session_state.form_gabarito)
    except ValueError:
      idx_gab = 0

    cad_gabarito = st.selectbox(
        "Gabarito Oficial", opcoes_gabarito_possiveis, index=idx_gab
    )
    cad_explicacao = st.text_area(
        "Explicação / Comentário",
        value=st.session_state.form_explicacao,
        height=100,
    )

    if st.form_submit_button("💾 Salvar Questão Definitivamente"):
      if cad_enunciado.strip() and op_a.strip() and op_b.strip():
        db.adicionar_questao(
            perfil_atual,
            cad_cargo,
            cad_materia,
            cad_enunciado,
            op_a,
            op_b,
            op_c,
            op_d,
            op_e,
            cad_gabarito,
            cad_explicacao,
        )
        st.success("Questão cadastrada com sucesso no banco de dados!")
      else:
        st.warning("Preencha o Enunciado e as Opções A e B!")

elif menu == "💾 Backup":
  st.title(f"💾 Gestão do Banco de Dados ({perfil_atual})")
  st.write(
      "Seus dados estão seguros na nuvem (Supabase). Utilize o painel do Supabase"
      " para gerenciar backups diretos do PostgreSQL."
  )