import sys
import sqlite3
import os
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableWidgetItem, 
                               QHeaderView, QAbstractItemView, QFileDialog)
import recursos_rc
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QDate, Qt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Image
from ofxparse import OfxParser
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

def resource_path(relative_path):
    """ Retorna o caminho correto para o arquivo dentro do EXE """
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
logo_path = resource_path("ramostransplogo25.png")

class FinsysApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- 1. CARREGAMENTO DA INTERFACE ---
        loader = QUiLoader()

        ui_path = resource_path("mainwindow.ui") 
        file = QFile(ui_path)

        if not file.exists():
            raise FileNotFoundError(f"Arquivo UI não encontrado: {ui_path}")

        file.open(QFile.ReadOnly)
        self.ui = loader.load(file)
        file.close()
        self.setCentralWidget(self.ui)

        # --- 2. CONFIGURAÇÕES VISUAIS ---
        self.setWindowTitle("Finsys")
        self.configurar_tabela(self.ui.tabelaRomaneio)
        self.configurar_tabela(self.ui.tableWidget)

        # --- 3. INICIALIZAÇÃO DE DADOS ---
        self.criar_banco()
        self.criar_banco_financeiro()

        # --- 4. CONEXÕES DE BOTÕES ---
        self.conectar_eventos()
        self.conectar_eventos_financeiros() # <-- AJUSTE 1: AGORA O DASHBOARD ESTÁ ATIVO!

        self.linha_em_edicao = -1

        # --- 5. CARREGAMENTO INICIAL ---
        self.atualizar_dashboard_mensal()
        self.atualizar_dashboard_anual() # <--- ADICIONE ESTA LINHA AQUI

        # --- 6. DEFINIR PÁGINA INICIAL ---
        self.ui.stackedWidget.setCurrentIndex(0)

        

    def criar_banco_financeiro(self):
            """Cria o banco de dados com o nome correto da coluna"""
            conexao = sqlite3.connect("financeiro_ramos.db")
            cursor = conexao.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transacoes (
                    id_ofx TEXT PRIMARY KEY,
                    data TEXT,
                    memo TEXT,
                    valor REAL,
                    tipo TEXT,
                    categoria TEXT
                )
            """)
            conexao.commit()
            conexao.close()

    def conectar_eventos_financeiros(self):
            # Conecta o botão de upload
            #self.ui.btn_upload_home.clicked.connect(self.importar_ofx)
            # Conecta o seletor da tela ANUAL
            self.ui.seletor_ano_anual.currentIndexChanged.connect(self.atualizar_dashboard_anual)
            # Conecta os seletores de mês e ano
            self.ui.messeletor_mes.currentIndexChanged.connect(self.atualizar_dashboard_mensal)
            self.ui.anoseletor_mes.currentIndexChanged.connect(self.atualizar_dashboard_mensal)

    def importar_ofx(self):
            caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Extrato", "", "Arquivos OFX (*.ofx)")
            if not caminho: return

            try:
                with open(caminho, 'rb') as f:
                    ofx = OfxParser.parse(f)

                conexao = sqlite3.connect("financeiro_ramos.db")
                cursor = conexao.cursor()

                for conta in ofx.accounts:
                    for tx in conta.statement.transactions:
                        val = float(tx.amount)
                        tipo = "Entrada" if val > 0 else "Saída"
                        desc = tx.memo.upper()
                        
                        # --- INTELIGÊNCIA DE CATEGORIA (PADRÃO RAMOS) ---
                        if tipo == "Entrada":
                            categoria = "PIX Recebido" if "PIX" in desc else "Rendimentos" if "JUROS" in desc else "Outros"
                        else:
                            if "COMPRA" in desc: categoria = "Débito"
                            elif "ENVIO PIX" in desc: categoria = "Transferência/Pagamento"
                            elif "PAG BOLETO" in desc or "PAGTO" in desc: categoria = "Contas Fixas"
                            else: categoria = "Pendente"

                        # AJUSTE DE INDENTAÇÃO: Agora o execute está fora do if/else, salvando TUDO
                        cursor.execute("""
                            INSERT OR IGNORE INTO transacoes (id_ofx, data, memo, valor, tipo, categoria)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (str(tx.id), tx.date.strftime("%d/%m/%Y"), tx.memo, val, tipo, categoria))

                conexao.commit()
                conexao.close()
                print("Extrato importado com sucesso!")
                self.atualizar_dashboard_mensal() 

            except Exception as e:
                print(f"Erro ao importar OFX: {e}")

    def atualizar_dashboard_mensal(self):
            # Pega o texto exato que está selecionado
            mes_texto = self.ui.messeletor_mes.currentText().strip().lower()
            ano = self.ui.anoseletor_mes.currentText()
            
            # Mapa rigoroso para garantir que Janeiro seja 01
            meses_map = {
                'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
                'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
                'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
            }
            
            mes_num = meses_map.get(mes_texto, "01")
            
            # O filtro busca a data no formato brasileiro salvo no banco: dd/mm/yyyy
            # Usamos %/mm/yyyy para garantir que pegue o mês certo
            filtro = f"%/{mes_num}/{ano}"
            
            print(f"DEBUG: Filtrando por {mes_texto} ({mes_num}) do ano {ano}. Filtro SQL: {filtro}")
            
            conexao = sqlite3.connect("financeiro_ramos.db")
            cursor = conexao.cursor()
            
            # 1. Soma Entradas do Mês Selecionado
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Entrada' AND data LIKE ?", (filtro,))
            res_e = cursor.fetchone()[0]
            total_e = float(res_e) if res_e else 0.0
            self.ui.valor_totalentradas_mes.setText(self.formatar_moeda_br(total_e))
            
            # 2. Soma Saídas do Mês Selecionado
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Saída' AND data LIKE ?", (filtro,))
            res_s = cursor.fetchone()[0]
            total_s = float(res_s) if res_s else 0.0
            self.ui.valor_totalsaidas_mes.setText(self.formatar_moeda_br(abs(total_s)))
            
            # 3. Saldo Geral e Cor do Status
            saldo = total_e + total_s # Saídas já são negativas no banco
            self.ui.statussituacao_mes.setText(self.formatar_moeda_br(saldo))
            
            # Estilização do Status (Lucro Verde / Prejuízo Vermelho)
            estilo_status = "background-color: #1A1A1A; color: #00c853; font-weight: bold; font-size: 16px;" if saldo >= 0 else "color: #ff1744; font-weight: bold; font-size: 16px;"
            self.ui.statussituacao_mes.setStyleSheet(estilo_status)
            
            # 4. Atualizar as Tabelas de Entrada e Saída
            self.preencher_tabela_dash(self.ui.entradasTab_mes, "Entrada", filtro)
            self.preencher_tabela_dash(self.ui.saidasTab_mes, "Saída", filtro)

            self.gerar_grafico_pizza(self.ui.grafEntr, filtro, "Entrada")
            self.gerar_grafico_pizza(self.ui.grafSaid, filtro, "Saída")
            
            conexao.close()

    def atualizar_dashboard_anual(self):
            """Calcula os totais do ano e atualiza a interface anual"""
            ano = self.ui.seletor_ano_anual.currentText()
            filtro_ano = f"%/{ano}"  # Filtra datas que terminam com /YYYY

            conexao = sqlite3.connect("financeiro_ramos.db")
            cursor = conexao.cursor()

            # 1. Soma Entradas do Ano
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Entrada' AND data LIKE ?", (filtro_ano,))
            res_e = cursor.fetchone()[0]
            total_e = float(res_e) if res_e else 0.0
            self.ui.valor_totalentradas_anual.setText(self.formatar_moeda_br(total_e))

            # 2. Soma Saídas do Ano
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Saída' AND data LIKE ?", (filtro_ano,))
            res_s = cursor.fetchone()[0]
            total_s = float(res_s) if res_s else 0.0
            self.ui.valor_totalsaidas_anual.setText(self.formatar_moeda_br(abs(total_s)))

            # 3. Saldo Anual e Status
            saldo = total_e + total_s
            self.ui.valor_saldo_anual.setText(self.formatar_moeda_br(saldo))

            # Estilo do Saldo Anual
            cor = "#00c853" if saldo >= 0 else "#ff1744"
            self.ui.valor_saldo_anual.setStyleSheet(f"color: {cor}; font-weight: bold; font-size: 18px; background: none;")

            conexao.close()

        # 4. Gera o Gráfico de Barras Comparativo
            self.gerar_grafico_barras_anual(self.ui.graficoevo, ano)

        # 5. Gerar Gráficos de Pizza Anuais (Principais Gastos e Entradas)
            self.gerar_grafico_pizza(self.ui.graf_principais_entradas_anual, filtro_ano, "Entrada")
            self.gerar_grafico_pizza(self.ui.graf_principais_gastos_anual, filtro_ano, "Saída")

    def gerar_grafico_barras_anual(self, widget_destino, ano):
        """Gera gráfico de colunas comparando Entradas e Saídas por mês"""
        import numpy as np
        conexao = sqlite3.connect("financeiro_ramos.db")
        cursor = conexao.cursor()

        meses_num = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
        entradas = []
        saidas = []

        for m in meses_num:
            filtro = f"%/{m}/{ano}"
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Entrada' AND data LIKE ?", (filtro,))
            entradas.append(cursor.fetchone()[0] or 0.0)
            
            cursor.execute("SELECT SUM(valor) FROM transacoes WHERE tipo='Saída' AND data LIKE ?", (filtro,))
            saidas.append(abs(cursor.fetchone()[0] or 0.0))

        conexao.close()

        # Preparação do Widget
        if widget_destino.layout() is None:
            from PySide6.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(widget_destino)
            layout.setContentsMargins(0,0,0,0)
            widget_destino.setLayout(layout)
        
        while widget_destino.layout().count():
            child = widget_destino.layout().takeAt(0)
            if child.widget(): child.widget().deleteLater()

        # Criação do Gráfico
        fig = Figure(figsize=(8, 4), dpi=100, facecolor='none')
        ax = fig.add_subplot(111)
        
        indices = np.arange(len(meses_num))
        largura = 0.35

        ax.bar(indices - largura/2, entradas, largura, label='Entradas', color='#0ed679')
        ax.bar(indices + largura/2, saidas, largura, label='Saídas', color='#ff3f46')

        ax.set_xticks(indices)
        ax.set_xticklabels(['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'], fontsize=8)
        ax.legend(fontsize=8, frameon=False)
        
        # Limpeza visual das bordas do gráfico
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        fig.tight_layout()
        canvas = FigureCanvas(fig)
        widget_destino.layout().addWidget(canvas)

    def preencher_tabela_dash(self, tabela, tipo, filtro):
        tabela.setRowCount(0)
        tabela.setColumnCount(4)
        tabela.setHorizontalHeaderLabels(["data", "descrição", "categoria", "valor"])
        
        header = tabela.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        conexao = sqlite3.connect("financeiro_ramos.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT data, memo, categoria, valor, id_ofx FROM transacoes WHERE tipo=? AND data LIKE ?", (tipo, filtro))
        
        lista_opcoes = [
            "Receita Frete", "PGMT Metall", "PGMT KBV", "PIX Recebido", "Rendimentos", "Débito", "Transferência/Pagamento",
            "Contas Fixas", "PGMT Motorista", "Lazer & Entretenimento", "Gastos Carros", "Alimentação", 
            "Educação", "Reserva", "Vestuario", "Assinaturas", "Transporte", "Saude", "Pendente"
        ]

        # --- VARIÁVEL DE CONTROLE PARA O ESPAÇAMENTO ---
        data_anterior = ""

        for row_data in cursor.fetchall():
            data_atual = str(row_data[0])

            # --- AJUSTE: INSERE LINHA EM BRANCO SE A DATA MUDAR ---
            if data_anterior != "" and data_atual != data_anterior:
                row_vazia = tabela.rowCount()
                tabela.insertRow(row_vazia)
                tabela.setRowHeight(row_vazia, 12) # Define a altura do "respiro"
                
                for col_vazia in range(4):
                    item_vazio = QTableWidgetItem("")
                    item_vazio.setFlags(Qt.NoItemFlags) # Bloqueia interação
                    item_vazio.setBackground(Qt.transparent)
                    tabela.setItem(row_vazia, col_vazia, item_vazio)
            
            data_anterior = data_atual
            # ---------------------------------------------------

            row = tabela.rowCount()
            tabela.insertRow(row)
            
            # Colunas de Texto (Data, Descrição e Valor)
            for col, val_index in {0: 0, 1: 1, 3: 3}.items():
                valor_raw = row_data[val_index]
                texto = self.formatar_moeda_br(abs(valor_raw)) if col == 3 else str(valor_raw)
                item = QTableWidgetItem(texto)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                
                if col == 3:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                
                tabela.setItem(row, col, item)

            from PySide6.QtWidgets import QComboBox
            combo = QComboBox()
            combo.addItems(lista_opcoes)
            
            if row_data[2] not in lista_opcoes:
                combo.addItem(row_data[2])
            combo.setCurrentText(row_data[2])
            
            combo.setStyleSheet("""
                QComboBox {
                    border: 0px;
                    border-radius: 0px;
                    padding: 2px 10px;
                    background-color: white;
                    font-family: "Montserrat Medium";
                    font-size: 16px;
                    min-height: 25px;
                }
                QComboBox::drop-down { border: none; }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #333;
                    margin-right: 10px;
                }
                QAbstractItemView {
                    background-color: white;
                    selection-background-color: #d32f2f;
                }
            """)
            combo.setProperty("id_tx", row_data[4])
            combo.currentTextChanged.connect(lambda text, c=combo: self.salvar_categoria_editada(text, c))
            
            tabela.setCellWidget(row, 2, combo)
            
        conexao.close()

    def salvar_categoria_editada(self, nova_categoria, combo_origem):
        id_tx = combo_origem.property("id_tx")
        
        conexao = sqlite3.connect("financeiro_ramos.db")
        cursor = conexao.cursor()
        cursor.execute("UPDATE transacoes SET categoria = ? WHERE id_ofx = ?", (nova_categoria, id_tx))
        conexao.commit()
        conexao.close()
        
        print(f"Categoria atualizada: {nova_categoria}")
        
        # --- SOLUÇÃO PARA NÃO PULAR O SCROLL ---
        # 1. Descobrimos qual tabela enviou o comando (Entradas ou Saídas)
        # Procuramos o "pai" do combobox até achar a tabela
        tabela = combo_origem.parent().parent() 
        
        # 2. Salva a posição atual da barra de rolagem vertical
        v_scroll = tabela.verticalScrollBar().value()
        
        # 3. Atualiza os dados (isso vai resetar a tabela)
        self.atualizar_dashboard_mensal()
        self.atualizar_dashboard_anual() # Caso esteja na aba anual também
        
        # 4. Devolve a barra de rolagem para onde ela estava
        tabela.verticalScrollBar().setValue(v_scroll)

    def configurar_tabela(self, tabela):

        """Padroniza a estrutura e ativa a estilização visual"""

        tabela.setColumnCount(4)
        tabela.setHorizontalHeaderLabels(["Data", "OS", "Destino", "Valor"])
        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        tabela.verticalHeader().setVisible(False)
        tabela.setShowGrid(False) 

        self.estilizar_tabela(tabela)

    def estilizar_tabela(self, tabela):

        """Aplica o design moderno com Montserrat e cores personalizadas"""

        estilo = """
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                selection-background-color: #d32f2f;
                selection-color: white;
                font-family: "Montserrat";
                font-size: 13px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }

            QHeaderView::section {
                background-color: #b71c1c;
                color: white;
                font-family: "Montserrat";
                font-weight: bold;
                text-transform: uppercase;
                padding: 10px;
                border: none;
            }

            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #f0f0f0;
            }

        """

        tabela.setStyleSheet(estilo)
        tabela.setAlternatingRowColors(True)

    def gerar_grafico_pizza(self, widget_destino, filtro_mes, tipo_transacao):
        """Gera gráfico de pizza com cores variadas e porcentagem na legenda"""
        conexao = sqlite3.connect("financeiro_ramos.db")
        cursor = conexao.cursor()
        cursor.execute(f"""
            SELECT categoria, SUM(ABS(valor)) 
            FROM transacoes 
            WHERE tipo='{tipo_transacao}' AND data LIKE ? 
            GROUP BY categoria
            ORDER BY SUM(ABS(valor)) DESC
        """, (filtro_mes,))
        dados = cursor.fetchall()
        conexao.close()

        if widget_destino.layout() is None:
            from PySide6.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(widget_destino)
            layout.setContentsMargins(0,0,0,0)
            widget_destino.setLayout(layout)
        
        while widget_destino.layout().count():
            child = widget_destino.layout().takeAt(0)
            if child.widget(): child.widget().deleteLater()

        if not dados: return

        categorias = [d[0] for d in dados]
        valores = [d[1] for d in dados]
        total = sum(valores)

        # 1. PALETA DE CORES VARIADA (Mistura de cores modernas e distintas)
        cores_variadas = [
            "#102831", "#0ed679", "#d8ab38", "#4e3a2a", '#e76f51', 
            "#ff22cf", '#1982c4', "#def867", "#ff3f46", '#5a189a'
        ]

        fig = Figure(figsize=(7, 4), dpi=100, facecolor='none')
        ax = fig.add_subplot(111)
        
        # 2. GRÁFICO (Sem texto em cima das fatias para não amontoar)
        wedges, texts = ax.pie(
            valores, 
            startangle=140, 
            colors=cores_variadas, 
            wedgeprops={'edgecolor': 'white', 'linewidth': 1.5}
        )
        
        # 3. LEGENDA DETALHADA (Nome + %)
        # Criamos os labels da legenda calculando a % de cada item
        labels_legenda = [f"{cat}: {(val/total)*100:1.1f}%" for cat, val in zip(categorias, valores)]

        ax.legend(
            wedges, 
            labels_legenda,
            title=f"Resumo de {tipo_transacao}s",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=8,
            frameon=False
        )
        
        # Efeito Rosca (opcional, deixa mais moderno)
        centre_circle = plt.Circle((0,0), 0.65, fc='white')
        fig.gca().add_artist(centre_circle)

        # Remove todas as margens extras da figura
        fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.05)
        
        # Se preferir uma solução automática mais agressiva, use:
        # fig.tight_layout(pad=0) 

        canvas = FigureCanvas(fig)
        widget_destino.layout().addWidget(canvas)

        # --- A MÁGICA DO MOUSE AQUI ---
        def on_hover(event):
            if event.inaxes == ax:
                for i, wedge in enumerate(wedges):
                    contem, _ = wedge.contains(event)
                    if contem:
                        valor_formatado = self.formatar_moeda_br(valores[i])
                        # Define a dica que aparece no mouse
                        canvas.setToolTip(f"<b>{categorias[i]}</b><br>Valor: {valor_formatado}<br>Percentual: {(valores[i]/total)*100:.1f}%")
                        return
                canvas.setToolTip("") # Limpa se não estiver em cima de nada

        # Conecta o evento de movimento do mouse ao canvas do gráfico
        canvas.mpl_connect("motion_notify_event", on_hover)

    def conectar_eventos(self):

        self.ui.btn_upload_home.clicked.connect(self.importar_ofx)

        """Centraliza todos os cliques de botões"""

        self.ui.btn_home.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(0))
        self.ui.btn_mensal.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(1))
        self.ui.btn_anual.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(2))
        self.ui.btn_romaneios.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(3))
        self.ui.btn_consulta_romaneios.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(4))

        self.ui.adicionarOS.clicked.connect(self.cadastrar_romaneio)
        self.ui.salvarPDF.clicked.connect(self.gerar_pdf)

        self.ui.btn_listar_consulta.clicked.connect(self.buscar_no_banco)
        self.ui.btn_limpar_consulta.clicked.connect(self.limpar_filtros_consulta)
        self.ui.btn_excluir_lancamento.clicked.connect(self.remover_linha_lancamento)

        # Detecta clique duplo para editar a linha

        self.ui.tabelaRomaneio.itemDoubleClicked.connect(self.preparar_edicao)

        # Criamos uma variável para controlar qual linha está sendo editada

        self.linha_em_edicao = -1

    def criar_banco(self):

        conexao = sqlite3.connect("dados_ramos.db")
        cursor = conexao.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS romaneios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT, os TEXT, destino TEXT, valor TEXT
            )
        """)

        conexao.commit()
        conexao.close()

    def remover_linha_lancamento(self):

        """Remove a linha selecionada da tabela de rascunho antes de salvar"""

        linha = self.ui.tabelaRomaneio.currentRow()
        if linha != -1:
            self.ui.tabelaRomaneio.removeRow(linha)
            self.atualizar_totais_lancamento() # Recalcula o rodapé automaticamente

    def formatar_moeda_br(self, valor_float):

        """Converte float para String R$ 1.234,56"""

        return f"R$ {valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def limpar_valor_para_float(self, texto):

        """Converte String R$ 1.234,56 para float 1234.56"""

        return float(texto.replace("R$ ", "").replace(".", "").replace(",", ".").strip())

    def buscar_no_banco(self):

        """Busca total: Se houver texto ou destino, ignora a data para garantir o resultado"""

        # 1. Pega os valores da tela

        destino_f = self.ui.combo_destino_consulta.currentText().strip()
        texto_busca = self.ui.lineEdit.text().strip()
        data_ini = self.ui.datainicial_consulta.date().toString("dd/MM/yyyy")
        data_fim = self.ui.datafinal_consulta.date().toString("dd/MM/yyyy")
       
        self.ui.tableWidget.setRowCount(0)
        total_valor = 0.0

        conexao = sqlite3.connect("dados_ramos.db")
        cursor = conexao.cursor()

        # --- LÓGICA DE PRIORIDADE MÁXIMA ---

        # 1. Se você digitou algo na busca por OS (lineEdit)

        if texto_busca != "":
            query = "SELECT data, os, destino, valor FROM romaneios WHERE os LIKE ?"
            parametros = (f"%{texto_busca}%",)
            print(f"Buscando por texto: {texto_busca}")

        # 2. Se você selecionou um destino específico

        elif destino_f != "Selecionar" and destino_f != "":
            query = "SELECT data, os, destino, valor FROM romaneios WHERE destino = ?"
            parametros = (destino_f,)
            print(f"Buscando por destino: {destino_f}")

        # 3. Se não tem texto nem destino, aí sim usamos o filtro de data

        else:

            # DICA: Se a busca por data falhar, é porque o SQL não entende dd/mm/yyyy no BETWEEN

            query = "SELECT data, os, destino, valor FROM romaneios WHERE data >= ? AND data <= ?"
            parametros = (data_ini, data_fim)
            print(f"Buscando por período: {data_ini} a {data_fim}")

        cursor.execute(query, parametros)
        resultados = cursor.fetchall()

        # Preenchimento da tabela

        for dados in resultados:
            row = self.ui.tableWidget.rowCount()
            self.ui.tableWidget.insertRow(row)
            for col, valor in enumerate(dados):
                texto_item = str(valor)
                if col == 3: # Formatação financeira
                    try:
                        v_float = self.limpar_valor_para_float(texto_item)
                        texto_item = self.formatar_moeda_br(v_float)
                        total_valor += v_float
                    except: pass

                item = QTableWidgetItem(texto_item)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter if col == 3 else Qt.AlignCenter)
                self.ui.tableWidget.setItem(row, col, item)

        conexao.close()

        # Totais do rodapé

        self.ui.valoros_consulta.setText(str(len(resultados)))
        self.ui.valorgeral_consulta.setText(self.formatar_moeda_br(total_valor))

    def limpar_filtros_consulta(self):

        self.ui.datainicial_consulta.setDate(QDate.currentDate())
        self.ui.datafinal_consulta.setDate(QDate.currentDate())
        self.ui.combo_destino_consulta.setCurrentIndex(0)
        self.ui.lineEdit.clear()
        self.ui.tableWidget.setRowCount(0)
        self.ui.valoros_consulta.setText("0")
        self.ui.valorgeral_consulta.setText("R$ 0,00")

    def cadastrar_romaneio(self):

        """Gerencia a inserção de novas linhas ou atualização de existentes"""

        os_num = self.ui.inserirOS.text()
        dest = self.ui.comboBox.currentText()
        val_raw = self.ui.inserirValor.text().replace(',', '.')
        data = self.ui.dateViagem.date().toString("dd/MM/yyyy")

        try:

            v_float = float(val_raw)
            val_final = self.formatar_moeda_br(v_float)

        except:

            val_final = f"R$ {val_raw}"

        tabela = self.ui.tabelaRomaneio

        # SE ESTIVER EDITANDO UMA LINHA EXISTENTE

        if self.linha_em_edicao != -1:
            tabela.setItem(self.linha_em_edicao, 0, QTableWidgetItem(data))
            tabela.setItem(self.linha_em_edicao, 1, QTableWidgetItem(os_num))
            tabela.setItem(self.linha_em_edicao, 2, QTableWidgetItem(dest))
            tabela.setItem(self.linha_em_edicao, 3, QTableWidgetItem(val_final))
           
            # Reset do estado do botão

            self.linha_em_edicao = -1
            self.ui.adicionarOS.setText("ADICIONAR")

            # Estilo Vermelho Padrão que você mostrou na imagem

            estilo_padrao = """

                QPushButton {
                    background-color: #b71c1c; /* Vermelho original */
                    color: white;
                    font-family: 'Montserrat';
                    font-weight: bold;
                    border: none;
                    padding: 5px;
                }

                QPushButton:hover {
                    background-color: #d32f2f;
                }

            """

            self.ui.adicionarOS.setStyleSheet(estilo_padrao)

        # SE FOR UMA LINHA NOVA

        else:
            row = tabela.rowCount()
            tabela.insertRow(row)

            # (Aqui você insere os QTableWidgetItem como já fazíamos antes...)

            tabela.setItem(row, 0, QTableWidgetItem(data))
            tabela.setItem(row, 1, QTableWidgetItem(os_num))
            tabela.setItem(row, 2, QTableWidgetItem(dest))
            tabela.setItem(row, 3, QTableWidgetItem(val_final))

        self.atualizar_totais_lancamento()
        self.ui.inserirOS.clear()
        self.ui.inserirValor.clear()

    def atualizar_totais_lancamento(self):

        tabela = self.ui.tabelaRomaneio
        total = 0.0

        for i in range(tabela.rowCount()):
            item = tabela.item(i, 3)
            if item:
                try:
                    total += self.limpar_valor_para_float(item.text())
                except: pass

        self.ui.valorOS.setText(str(tabela.rowCount()))
        self.ui.valorGer.setText(self.formatar_moeda_br(total))



    def gerar_pdf(self):
        nome_arquivo = "ramostransportes_romaneios.pdf"
        pdf = canvas.Canvas(nome_arquivo, pagesize=A4)
        largura, altura = A4
        tabela = self.ui.tabelaRomaneio

        data_inicio_nota = ""

        if tabela.rowCount() > 0:
            item_data = tabela.item(0, 0)

        if item_data:
            data_inicio_nota = item_data.text()

        print("LOGO PATH:", logo_path)
        print("EXISTE?", os.path.exists(logo_path))

        # --- LOGO (CAMINHO CORRETO E DEFINITIVO) ---

        if os.path.exists(logo_path):

            pdf.drawImage(
                logo_path,
                50,
                altura - 90,
                width=90,
                height=60,
                preserveAspectRatio=True,
                mask='auto'
            )

        else:

            print("ERRO: logo não encontrada em:", logo_path)
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(50, altura - 65, "RAMOS TRANSPORTES")

        # --- CABEÇALHO ---

        pdf.setFont("Helvetica", 12)
        pdf.drawString(160, altura - 60, "romaneios - Paulo")
        pdf.drawString(380, altura - 60, "início da nota")
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(470, altura - 60, data_inicio_nota)

        # Linha vermelha

        pdf.setStrokeColor(colors.red)
        pdf.setLineWidth(1.5)
        pdf.line(50, altura - 100, 550, altura - 100)
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.5)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(largura / 2, altura - 115, "valores já combinados")

        # --- TABELA ---

        y = altura - 145
        data_anterior = ""

        for i in range(tabela.rowCount()):

            data_at = tabela.item(i, 0).text()
            os_n = tabela.item(i, 1).text()
            dest = tabela.item(i, 2).text().upper()
            val_f = tabela.item(i, 3).text()

            if data_at != data_anterior:

                y -= 25 if data_anterior else 10
                pdf.rect(480, y, 70, 15)
                pdf.setFont("Helvetica-Bold", 8)
                pdf.drawCentredString(515, y + 4, f"dia {data_at[:5]}")
                data_anterior = data_at

            pdf.setFont("Helvetica", 9)
            pdf.rect(50, y - 20, 30, 20); pdf.drawCentredString(65, y - 14, str(i + 1))
            pdf.rect(80, y - 20, 35, 20); pdf.drawCentredString(97.5, y - 14, "OS")
            pdf.rect(115, y - 20, 120, 20); pdf.drawCentredString(175, y - 14, os_n)
            pdf.rect(235, y - 20, 175, 20); pdf.drawCentredString(322.5, y - 14, dest[:35])
            pdf.rect(410, y - 20, 70, 20); pdf.drawCentredString(445, y - 14, data_at)
            pdf.rect(480, y - 20, 70, 20); pdf.drawCentredString(515, y - 14, val_f)

            y -= 20

            if y < 100:
                pdf.showPage()
                y = altura - 80
                data_anterior = ""

        # --- RODAPÉ DINÂMICO (ACOMPANHA A TABELA) ---

        y_f = y - 30  # espaço abaixo da última OS

        # Se estiver muito perto do fim da página, quebra

        if y_f < 80:
            pdf.showPage()
            y_f = altura - 120

        pdf.setFont("Helvetica", 12)
        pdf.rect(50, y_f, 200, 25)
        pdf.drawCentredString(150, y_f + 8, "encerramento da nota")
        pdf.rect(250, y_f, 100, 25)
        pdf.drawString(255, y_f + 8, f"qtd OS's: {self.ui.valorOS.text()}")
        pdf.rect(350, y_f, 200, 25)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(355, y_f + 8, "total Geral")
        pdf.drawRightString(545, y_f + 8, self.ui.valorGer.text())

        pdf.save()
        webbrowser.open(nome_arquivo)

    def preparar_edicao(self, item):

        """Retorna os dados da tabela para os campos e estiliza o botão de forma profissional"""

        self.linha_em_edicao = item.row()
        tabela = self.ui.tabelaRomaneio

        # Puxa os dados da linha clicada

        data_texto = tabela.item(self.linha_em_edicao, 0).text()
        os_texto = tabela.item(self.linha_em_edicao, 1).text()
        destino_texto = tabela.item(self.linha_em_edicao, 2).text()
        valor_texto = tabela.item(self.linha_em_edicao, 3).text().replace("R$ ", "")

        # Preenche os widgets de entrada

        self.ui.dateViagem.setDate(QDate.fromString(data_texto, "dd/MM/yyyy"))
        self.ui.inserirOS.setText(os_texto)
        self.ui.comboBox.setCurrentText(destino_texto)
        self.ui.inserirValor.setText(valor_texto)

        # --- ESTILO PARA O BOTÃO EM MODO EDIÇÃO ---

        # Aqui mantemos a Montserrat e o arredondamento, mudando apenas a cor para um verde elegante

        estilo_edicao = """
            QPushButton {
                background-color: #2e7d32;
                color: white;
                font-family: 'Montserrat';
                font-weight: bold;
                border-radius: 0px;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: #1b5e20;

            }
        """

        self.ui.adicionarOS.setText("atualizar")
        self.ui.adicionarOS.setStyleSheet(estilo_edicao)

if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = FinsysApp()
    window.show()
    sys.exit(app.exec())