import datetime
import os
import re
import psycopg2
from google import genai
from google.genai import types
from PIL import Image
import streamlit as st

# ==============================================================================
# BACKEND: GERENCIADOR DO SUPABASE (POSTGRESQL) E IA
# ==============================================================================
class DatabaseManager:
    def __init__(self):
        self.conn_str = st.secrets["supabase"]["connection_string"]

    def get_connection(self):
        return psycopg2.connect(self.conn_str)

    # ... (Mantenha todos os seus métodos aqui: resolver_questao_com_ia, salvar_config_geral, etc.)
    # [O código do DatabaseManager permanece o mesmo que você enviou]
    
    # (Inseri aqui apenas a estrutura para representar que seus métodos continuam abaixo)
    def resolver_questao_com_ia(self, enunciado, opcoes_dict):
        # ... (seu código original)
        pass

    def processar_texto_questao_com_ia(self, texto_bruto):
        # ... (seu código original)
        pass

    def ler_questao_por_imagem(self, image_path):
        # ... (seu código original)
        pass

    def salvar_config_geral(self, chave, valor):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO config_geral (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor", (chave, valor))
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

    def salvar_config_edital(self, materia, qtd_questoes, peso):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO edital_config (materia, qtd_questoes, peso) VALUES (%s, %s, %s) ON CONFLICT (materia) DO UPDATE SET qtd_questoes = EXCLUDED.qtd_questoes, peso = EXCLUDED.peso", (materia.strip(), int(qtd_questoes), float(peso)))
                conn.commit()

    def remover_materia_edital(self, materia):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM edital_config WHERE materia = %s", (materia,))
                conn.commit()

    def obter_configs_edital(self, cargo=None):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    if cargo and cargo != "Não definido" and cargo.strip() != "":
                        cursor.execute("SELECT materia, qtd_questoes, peso FROM edital_config WHERE cargo = %s", (cargo.strip(),))
                    else:
                        cursor.execute("SELECT materia, qtd_questoes, peso FROM edital_config")
                except Exception:
                    conn.rollback()
                    cursor.execute("SELECT materia, qtd_questoes, peso FROM edital_config")
                return {row[0]: {"qtd": row[1], "peso": row[2]} for row in cursor.fetchall()}

    def registrar_resposta(self, questao_id, resposta_usuario):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT gabarito, total_erros, erros_consecutivos, total_tentativas FROM questoes WHERE id = %s", (questao_id,))
                res = cursor.fetchone()
                if not res: return False, 0, 0
                gabarito, total_erros, erros_cons, total_tent = res
                acertou = 1 if resposta_usuario.strip().upper() == gabarito.strip().upper() else 0
                novo_total_tent = (total_tent or 0) + 1
                novo_erros_cons = 0 if acertou else (erros_cons or 0) + 1
                novo_total_erros = (total_erros or 0) + (0 if acertou else 1)
                cursor.execute("UPDATE questoes SET total_erros = %s, erros_consecutivos = %s, total_tentativas = %s WHERE id = %s", (novo_total_erros, novo_erros_cons, novo_total_tent, questao_id))
                cursor.execute("INSERT INTO historico_respostas (questao_id, resposta_usuario, acertou) VALUES (%s, %s, %s)", (questao_id, resposta_usuario.upper(), acertou))
                conn.commit()
                return bool(acertou), novo_erros_cons, novo_total_erros

    def obter_questoes(self, cargo=None, materia=None, apenas_reincidentes=False):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                query = "SELECT id, cargo, materia, enunciado, opcao_a, opcao_b, opcao_c, opcao_d, opcao_e, gabarito, explicacao, total_tentativas, total_erros, erros_consecutivos FROM questoes WHERE 1=1"
                params = []
                if cargo and cargo not in ["Todos", "Cargo / Concurso", "Nenhum cargo cadastrado"]:
                    query += " AND cargo = %s"; params.append(cargo)
                if materia and materia != "Todas":
                    query += " AND materia = %s"; params.append(materia)
                if apenas_reincidentes: query += " AND erros_consecutivos >= 2"
                query += " ORDER BY RANDOM()"
                cursor.execute(query, params)
                return cursor.fetchall()

    def obter_cargos(self):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT cargo FROM questoes WHERE cargo IS NOT NULL AND cargo != '' ORDER BY cargo")
                return [row[0] for row in cursor.fetchall()]

    def obter_cargos_totais(self):
        cargos_set = set()
        nome_conc = self.obter_config_geral("nome_concurso", "")
        if nome_conc and nome_conc != "Não definido" and nome_conc.strip() != "": cargos_set.add(nome_conc)
        for c in self.obter_cargos():
            if c: cargos_set.add(c)
        return sorted(list(cargos_set))

    def obter_materias(self, cargo=None):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if cargo and cargo not in ["Todos", "Cargo / Concurso"]:
                    cursor.execute("SELECT DISTINCT materia FROM questoes WHERE cargo = %s AND materia IS NOT NULL AND materia != '' ORDER BY materia", (cargo,))
                    materias_banco = [row[0] for row in cursor.fetchall()]
                else:
                    cursor.execute("SELECT DISTINCT materia FROM questoes WHERE materia IS NOT NULL AND materia != '' ORDER BY materia")
                    materias_banco = [row[0] for row in cursor.fetchall()]
                cursor.execute("SELECT materia FROM edital_config")
                materias_edital = [row[0] for row in cursor.fetchall()]
                return sorted(list(set(materias_banco + materias_edital)))

    def adicionar_questao(self, cargo, materia, enunciado, op_a, op_b, op_c, op_d, op_e, gabarito, explicacao):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO questoes (cargo, materia, enunciado, opcao_a, opcao_b, opcao_c, opcao_d, opcao_e, gabarito, explicacao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (cargo.strip(), materia.strip(), enunciado, op_a, op_b, op_c, op_d, op_e, gabarito.upper(), explicacao))
                conn.commit()

    def deletar_questao(self, questao_id):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM historico_respostas WHERE questao_id = %s", (questao_id,))
                cursor.execute("DELETE FROM questoes WHERE id = %s", (questao_id,))
                conn.commit()

    def deletar_materia_edital(self, materia):
        self.remover_materia_edital(materia)

    def obter_analise_dashboard(self):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                configs = self.obter_configs_edital()
                materias = self.obter_materias()
                detalhes_materias = []
                materia_mais_critica = "Nenhuma"
                max_pontos_perdidos = -1.0
                pontuacao_maxima_prova = 0.0
                pontuacao_projetada = 0.0
                total_erros_geral = 0
                total_tentativas_geral = 0
                cursor.execute("SELECT COUNT(id) FROM questoes WHERE explicacao IS NOT NULL AND TRIM(explicacao) != ''")
                total_comentadas = cursor.fetchone()[0] or 0
                for mat in materias:
                    cfg = configs.get(mat, {"qtd": 0, "peso": 1.0})
                    qtd_prova = cfg["qtd"]
                    peso = cfg["peso"]
                    cursor.execute("SELECT COUNT(id), SUM(total_tentativas), SUM(total_erros) FROM questoes WHERE materia = %s", (mat,))
                    q_cad, tent, erros = cursor.fetchone()
                    q_cad = q_cad or 0; tent = tent or 0; erros = erros or 0; acertos = tent - erros
                    total_erros_geral += erros; total_tentativas_geral += tent
                    pontos_possiveis_mat = qtd_prova * peso
                    pontuacao_maxima_prova += pontos_possiveis_mat
                    if tent > 0:
                        taxa_acerto = (acertos / tent) * 100.0
                        pontos_estimados_mat = pontos_possiveis_mat * (taxa_acerto / 100.0)
                        pontos_perdidos_mat = pontos_possiveis_mat - pontos_estimados_mat
                    else:
                        taxa_acerto = 0.0; pontos_estimados_mat = 0.0; pontos_perdidos_mat = 0.0
                    pontuacao_projetada += pontos_estimados_mat
                    if tent > 0 and pontos_perdidos_mat > max_pontos_perdidos and taxa_acerto < 100.0:
                        max_pontos_perdidos = pontos_perdidos_mat; materia_mais_critica = mat
                    detalhes_materias.append({"materia": mat, "qtd_prova": qtd_prova, "peso": peso, "q_cadastradas": q_cad, "tentativas": tent, "certas": acertos, "erradas": erros, "taxa_acerto": taxa_acerto, "pontos_possiveis": pontos_possiveis_mat, "pontos_estimados": pontos_estimados_mat, "pontos_perdidos": pontos_perdidos_mat})
                nome_concurso = self.obter_config_geral("nome_concurso", "Não definido")
                certas_geral = total_tentativas_geral - total_erros_geral
                taxa_global = (certas_geral / total_tentativas_geral * 100.0) if total_tentativas_geral > 0 else 0.0
                return {"nome_concurso": nome_concurso, "materias_detalhes": detalhes_materias, "materia_mais_critica": materia_mais_critica if max_pontos_perdidos > 0 else "Nenhuma", "pontuacao_projetada": pontuacao_projetada, "pontuacao_maxima": pontuacao_maxima_prova, "total": total_tentativas_geral, "certas": certas_geral, "erradas": total_erros_geral, "comentadas": total_comentadas, "taxa_global": taxa_global}

@st.cache_resource
def get_db():
    return DatabaseManager()

db = get_db()

# --- FUNÇÕES CACHEADAS ---
@st.cache_data(ttl=60)
def cached_obter_analise_dashboard():
    return db.obter_analise_dashboard()

@st.cache_data(ttl=60)
def cached_obter_questoes(cargo, materia, apenas_reincidentes):
    return db.obter_questoes(cargo, materia, apenas_reincidentes)

@st.cache_data(ttl=300)
def cached_obter_cargos_totais():
    return db.obter_cargos_totais()

@st.cache_data(ttl=300)
def cached_obter_materias(cargo):
    return db.obter_materias(cargo)