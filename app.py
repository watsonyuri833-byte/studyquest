import datetime
import os
import re
import psycopg2
from google import genai
from google.genai import types
from PIL import Image
import streamlit as st

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
      client = genai.Client()
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
          model="gemini-2.0-flash",
          contents=prompt,
          config=types.GenerateContentConfig(temperature=0.1),
      )
      return response.text
    except Exception as e:
      return f"Erro ao consultar a IA: {str(e)}"

  def processar_texto_questao_com_ia(self, texto_bruto):
    try:
      client = genai.Client()
      prompt = f"""
            Atue como um especialista em processamento de dados para concursos públicos. 
            Analise o texto bruto da questão abaixo e organize-o obrigatoriamente no seguinte formato estruturado:
            ENUNCIADO: [Texto limpo do enunciado da questão]
            ALTERNATIVA_A: [Texto da opção A sem a letra inicial]
            ALTERNATIVA_B: [Texto da opção B sem a letra inicial]
            ALTERNATIVA_C: [Texto da opção C sem a letra inicial, ou deixe vazio se não houver]
            ALTERNATIVA_D: [Texto da opção D sem a letra inicial, ou deixe vazio se não houver]
            ALTERNATIVA_E: [Texto da opção E sem a letra inicial, ou deixe vazio se não houver]
            GABARITO: [Apenas a letra correta se indicada, ex: A, B, C, D ou E]
            EXPLICACAO: [Explicação ou comentário se houver no texto, ou deixe vazio]

            Texto Bruto da Questão:
            {texto_bruto}
            """
      response = client.models.generate_content(
          model="gemini-2.0-flash",
          contents=prompt,
          config=types.GenerateContentConfig(temperature=0.1),
      )
      return response.text
    except Exception as e:
      return f"Erro ao processar texto com IA: {str(e)}"

  def ler_questao_por_imagem(self, image_path):
    try:
      client = genai.Client()
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
          model="gemini-2.0-flash",
          contents=[prompt, imagem],
          config=types.GenerateContentConfig(temperature=0.1),
      )
      return response.text
    except Exception as e:
      return f"Erro ao processar imagem com IA: {str(e)}"

  def salvar_config_geral(self, chave, valor):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO config_geral (chave, valor)
                VALUES (%s, %s)
                ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
            """,
            (chave, valor),
        )
        conn.commit()

  def remover_config_geral(self, chave):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute("DELETE FROM config_geral WHERE chave = %s", (chave,))
        conn.commit()

  def obter_config_geral(self, chave, default=""):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute("SELECT valor FROM config_geral WHERE chave = %s", (chave,))
        res = cursor.fetchone()
        return res[0] if res else default

  def salvar_config_edital(self, concurso_nome, materia, qtd_questoes, peso):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO edital_config (concurso_nome, materia, qtd_questoes, peso)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (concurso_nome, materia) DO UPDATE SET
                    qtd_questoes = EXCLUDED.qtd_questoes,
                    peso = EXCLUDED.peso
            """,
            (concurso_nome.strip(), materia.strip(), int(qtd_questoes), float(peso)),
        )
        conn.commit()

  def remover_materia_edital(self, concurso_nome, materia):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM edital_config WHERE concurso_nome = %s AND materia = %s",
            (concurso_nome, materia),
        )
        conn.commit()

  def deletar_concurso_inteiro(self, concurso_nome):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM edital_config WHERE concurso_nome = %s", (concurso_nome,)
        )
        conn.commit()

  def obter_configs_edital(self, concurso_nome=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if concurso_nome and concurso_nome != "Todos" and concurso_nome.strip():
          cursor.execute(
              "SELECT materia, qtd_questoes, peso FROM edital_config WHERE concurso_nome = %s",
              (concurso_nome.strip(),),
          )
        else:
          cursor.execute("SELECT materia, qtd_questoes, peso FROM edital_config")
        return {
            row[0]: {"qtd": row[1], "peso": row[2]} for row in cursor.fetchall()
        }

  def obter_concursos_cadastrados(self):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT concurso_nome FROM edital_config UNION SELECT"
            " DISTINCT cargo FROM questoes WHERE cargo IS NOT NULL AND cargo !=''"
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
        return bool(acertou), novo_erros_cons, novo_total_erros

  def obter_questoes(
      self, cargo=None, materia=None, apenas_reincidentes=False
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        query = (
            "SELECT id, cargo, materia, enunciado, opcao_a, opcao_b, opcao_c,"
            " opcao_d, opcao_e, gabarito, explicacao, total_tentativas,"
            " total_erros, erros_consecutivos FROM questoes WHERE 1=1"
        )
        params = []
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
        if apenas_reincidentes:
          query += " AND erros_consecutivos >= 2"
        query += " ORDER BY RANDOM()"
        cursor.execute(query, params)
        return cursor.fetchall()

  def obter_cargos(self):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT cargo FROM questoes WHERE cargo IS NOT NULL AND"
            " cargo != '' ORDER BY cargo"
        )
        return [row[0] for row in cursor.fetchall()]

  def obter_cargos_totais(self):
    cargos_set = set(self.obter_concursos_cadastrados())
    for c in self.obter_cargos():
      if c:
        cargos_set.add(c)
    return sorted(list(cargos_set))

  def obter_materias(self, cargo=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        if cargo and cargo != "Todos" and cargo != "Cargo / Concurso":
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE cargo = %s AND"
              " materia IS NOT NULL AND materia != '' ORDER BY materia",
              (cargo,),
          )
          materias_banco = [row[0] for row in cursor.fetchall()]
        else:
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE materia IS NOT NULL"
              " AND materia != '' ORDER BY materia"
          )
          materias_banco = [row[0] for row in cursor.fetchall()]

        configs = self.obter_configs_edital(cargo)
        materias_edital = list(configs.keys())
        return sorted(list(set(materias_banco + materias_edital)))

  def adicionar_questao(
      self,
      cargo,
      materia,
      enunciado,
      op_a,
      op_b,
      op_c,
      op_d,
      op_e,
      gabarito,
      explicacao,
  ):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO questoes (cargo, materia, enunciado, opcao_a, opcao_b, opcao_c, opcao_d, opcao_e, gabarito, explicacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
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

  def deletar_questao(self, questao_id):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM historico_respostas WHERE questao_id = %s",
            (questao_id,),
        )
        cursor.execute("DELETE FROM questoes WHERE id = %s", (questao_id,))
        conn.commit()

  def obter_analise_dashboard(self, concurso_ativo=None):
    with self.get_connection() as conn:
      with conn.cursor() as cursor:
        configs = self.obter_configs_edital(concurso_ativo)
        materias_edital = list(configs.keys())

        if concurso_ativo and concurso_ativo != "Todos":
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE cargo = %s AND"
              " materia IS NOT NULL",
              (concurso_ativo,),
          )
        else:
          cursor.execute(
              "SELECT DISTINCT materia FROM questoes WHERE materia IS NOT NULL"
          )
        materias_questoes = [row[0] for row in cursor.fetchall()]
        materias = sorted(list(set(materias_edital + materias_questoes)))

        detalhes_materias = []
        materia_mais_critica = "Nenhuma"
        max_pontos_perdidos = -1.0
        pontuacao_maxima_prova = 0.0
        pontuacao_projetada = 0.0
        total_erros_geral = 0
        total_tentativas_geral = 0

        if concurso_ativo and concurso_ativo != "Todos":
          cursor.execute(
              "SELECT COUNT(id) FROM questoes WHERE cargo = %s AND explicacao IS"
              " NOT NULL AND TRIM(explicacao) != ''",
              (concurso_ativo,),
          )
        else:
          cursor.execute(
              "SELECT COUNT(id) FROM questoes WHERE explicacao IS NOT NULL AND"
              " TRIM(explicacao) != ''"
          )
        total_comentadas = cursor.fetchone()[0] or 0

        for mat in materias:
          cfg = configs.get(mat, {"qtd": 0, "peso": 1.0})
          qtd_prova = cfg["qtd"]
          peso = cfg["peso"]

          if concurso_ativo and concurso_ativo != "Todos":
            cursor.execute(
                """
                        SELECT COUNT(id), SUM(total_tentativas), SUM(total_erros) 
                        FROM questoes WHERE cargo = %s AND materia = %s
                    """,
                (concurso_ativo, mat),
            )
          else:
            cursor.execute(
                """
                        SELECT COUNT(id), SUM(total_tentativas), SUM(total_erros) 
                        FROM questoes WHERE materia = %s
                    """,
                (mat,),
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
            materia_mais_critica = mat

          detalhes_materias.append({
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


@st.cache_resource
def get_db():
  return DatabaseManager()


db = get_db()


# --- FUNÇÕES CACHEADAS ---
@st.cache_data(ttl=60)
def cached_obter_analise_dashboard(concurso_ativo):
  return db.obter_analise_dashboard(concurso_ativo)


@st.cache_data(ttl=60)
def cached_obter_questoes(cargo, materia, apenas_reincidentes):
  return db.obter_questoes(cargo, materia, apenas_reincidentes)


@st.cache_data(ttl=300)
def cached_obter_cargos_totais():
  return db.obter_cargos_totais()


@st.cache_data(ttl=300)
def cached_obter_materias(cargo):
  return db.obter_materias(cargo)


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
  st.session_state.concurso_selecionado = "Geral"

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
menu = st.sidebar.radio(
    "Navegação", ["📊 Dashboard", "📖 Questões", "➕ Cadastrar", "💾 Backup"]
)

if menu == "📊 Dashboard":
  st.title("📊 Dashboard & Análise Estratégica")

  # --- GERENCIADOR DE MÚLTIPLOS CONCURSOS ---
  cargos_cadastrados = db.obter_concursos_cadastrados()
  opcoes_concurso = ["Geral (Todos)"] + cargos_cadastrados

  with st.container(border=True):
    st.subheader("🎯 Seleção e Gestão de Concursos")
    col_sel, col_novo, col_del = st.columns([3, 3, 2])

    with col_sel:
      # Sincronizar índice atual
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
          # Adiciona uma matéria padrão ou apenas salva no state/edital para criá-lo
          db.salvar_config_edital(
              novo_concurso_input.strip(), "Geral", 10, 1.0
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
        db.deletar_concurso_inteiro(st.session_state.concurso_selecionado)
        st.success("Concurso excluído!")
        st.session_state.concurso_selecionado = "Geral (Todos)"
        st.rerun()

  ativo_param = (
      None
      if st.session_state.concurso_selecionado == "Geral (Todos)"
      else st.session_state.concurso_selecionado
  )
  dados = cached_obter_analise_dashboard(ativo_param)

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

  c_info1, c_info2 = st.columns(2)
  with c_info1:
    with st.container(border=True):
      st.metric(
          "🎯 PONTUAÇÃO PROJETADA VS MÁXIMA",
          f"{dados['pontuacao_projetada']:.1f} / {dados['pontuacao_maxima']:.1f}",
      )
  with c_info2:
    with st.container(border=True):
      st.metric("⚠️ PONTO CEGO (MAIOR DEFICIT)", dados["materia_mais_critica"])

  st.markdown("---")

  # --- FORMULÁRIO DE ADICIONAR MATÉRIAS AO CONCURSO ATIVO ---
  with st.container(border=True):
    st.subheader(
        f"⚙️ Configurar Edital do Concurso: {st.session_state.concurso_selecionado}"
    )

    if st.session_state.concurso_selecionado == "Geral (Todos)":
      st.info(
          "Selecione um concurso específico acima para adicionar matérias ao"
          " edital correspondente."
      )
    else:
      with st.form("form_edital_multi"):
        st.markdown("##### Adicionar / Atualizar Matéria")
        f1, f2, f3 = st.columns([3, 1, 1])
        with f1:
          mat_input = st.text_input("Nome da Matéria (ex: Direito Administrativo)")
        with f2:
          qtd_input = st.text_input("Qtd Questões na Prova", value="10")
        with f3:
          peso_input = st.text_input("Peso da Matéria", value="1.0")

        btn_salvar_edital = st.form_submit_button("+ Adicionar Matéria ao Edital")
        if btn_salvar_edital:
          if mat_input.strip() and qtd_input.strip() and peso_input.strip():
            try:
              db.salvar_config_edital(
                  st.session_state.concurso_selecionado,
                  mat_input.strip(),
                  int(qtd_input),
                  float(peso_input),
              )
              st.success(
                  f"Matéria '{mat_input.strip()}' adicionada ao edital de"
                  f" '{st.session_state.concurso_selecionado}'!"
              )
              st.rerun()
            except ValueError:
              st.error("Quantidade deve ser inteiro e Peso deve ser decimal.")
          else:
            st.warning("Preencha todos os campos da matéria!")

  st.markdown("---")
  titulo_analise = (
      f"📋 Rendimento por Matéria — {st.session_state.concurso_selecionado}"
  )
  st.subheader(titulo_analise)

  for item in dados["materias_detalhes"]:
    with st.container(border=True):
      cols = st.columns([3, 1])
      with cols[0]:
        st.markdown(f"### 📚 {item['materia']}")
        taxa_mat = item["taxa_acerto"]
        st.progress(
            int(taxa_mat) if taxa_mat <= 100 else 100,
            text=f"Taxa: {taxa_mat:.1f}%",
        )
        txt_stats = (
            f"**Acertos:** {item.get('certas', 0)} | **Erros:**"
            f" {item.get('erradas', 0)} | **Total Resolvidas:** {item['tentativas']} | **Edital:** {item['qtd_prova']}"
            f" q. (Peso {item['peso']:.1f})"
        )
        st.markdown(txt_stats)
      with cols[1]:
        st.markdown("<br>", unsafe_allow_html=True)
        if (
            st.session_state.concurso_selecionado != "Geral (Todos)"
            and st.button("🗑️ Excluir Matéria", key=f"del_mat_{item['materia']}")
        ):
          db.remover_materia_edital(
              st.session_state.concurso_selecionado, item["materia"]
          )
          st.rerun()

elif menu == "📖 Questões":
  st.title("📖 Resolução de Questões")
  cargos = ["Todos"] + cached_obter_cargos_totais()
  f_col1, f_col2, f_col3, f_col4 = st.columns([2, 2, 2, 2])
  with f_col1:
    cargo_filtro = st.selectbox("Cargo / Concurso", cargos)
  with f_col2:
    mats = ["Todas"] + cached_obter_materias(
        cargo=cargo_filtro if cargo_filtro != "Todos" else None
    )
    materia_filtro = st.selectbox("Matéria", mats)
  with f_col3:
    apenas_reincidentes = st.checkbox("⚠️ Erros 2x+")
  with f_col4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 Carregar Questões", use_container_width=True):
      st.session_state.questoes_lista = cached_obter_questoes(
          cargo_filtro, materia_filtro, apenas_reincidentes
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
            f" **Questão {idx + 1} de {len(st.session_state.questoes_lista)}** |"
            f" **Erros:** {total_erros or 0}"
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
  st.title("➕ Nova Questão & Automação Inteligente")

  with st.expander("📝 Colar Texto Completo da Questão", expanded=True):
    texto_bruto_input = st.text_area(
        "Cole aqui o texto inteiro da questão:", height=150
    )
    if st.button("⚡ Processar e Separar com IA"):
      if texto_bruto_input.strip():
        with st.spinner("A IA está analisando e separando o texto..."):
          resultado_analise = db.processar_texto_questao_com_ia(texto_bruto_input)
          if resultado_analise.startswith("Erro"):
            st.error(resultado_analise)
          else:
            texto_limpo_ia = (
                resultado_analise.replace("**", "")
                .replace("*", "")
                .replace("`", "")
            )

            def extrair_tag(tag, texto):
              pattern = (
                  rf"(?:^|\n)\s*{tag}\s*:\s*(.*?)(?=\n\s*[A-Z_]{3,}\s*:|\Z)"
              )
              match = re.search(pattern, texto, re.DOTALL | re.IGNORECASE)
              return match.group(1).strip() if match else ""

            st.session_state.form_enunciado = (
                extrair_tag("ENUNCIADO", texto_limpo_ia) or texto_bruto_input
            )
            st.session_state.form_op_a = extrair_tag(
                "ALTERNATIVA_A", texto_limpo_ia
            )
            st.session_state.form_op_b = extrair_tag(
                "ALTERNATIVA_B", texto_limpo_ia
            )
            st.session_state.form_op_c = extrair_tag(
                "ALTERNATIVA_C", texto_limpo_ia
            )
            st.session_state.form_op_d = extrair_tag(
                "ALTERNATIVA_D", texto_limpo_ia
            )
            st.session_state.form_op_e = extrair_tag(
                "ALTERNATIVA_E", texto_limpo_ia
            )
            gab = extrair_tag("GABARITO", texto_limpo_ia).upper()
            if gab and gab[0] in ["A", "B", "C", "D", "E"]:
              st.session_state.form_gabarito = gab[0]
            st.session_state.form_explicacao = extrair_tag(
                "EXPLICACAO", texto_limpo_ia
            )
            st.success("Texto processado com sucesso!")
            st.rerun()

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

  cargos_iniciais = db.obter_cargos_totais()
  if not cargos_iniciais:
    cargos_iniciais = ["Cargo / Concurso"]

  st.markdown("---")
  st.subheader("📝 Formulário de Revisão e Cadastro")
  cad_cargo = st.selectbox(
      "Cargo / Concurso", cargos_iniciais, key="cad_cargo_select"
  )
  materias_cargo = cached_obter_materias(cargo=cad_cargo)
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
  st.title("💾 Gestão do Banco de Dados")
  st.write(
      "Seus dados estão seguros na nuvem (Supabase). Utilize o painel do Supabase"
      " para gerenciar backups diretos do PostgreSQL."
  )