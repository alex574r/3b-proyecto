"""Ventana para analizar carpetas de fotos: python gui.py

Elige una carpeta con fotos <ID>_facade/_product/_shelf.jpg (como Validat3B_desarrollo_imagenes), analiza cada captura con el
motor y guarda un JSON por captura en salida_carpetas/<nombre de la carpeta>/ dentro del proyecto.
Con Haiku activo hace falta FOUNDRY_API_KEY en el entorno; sin ella solo corren los chequeos locales.
"""
import json
import os
import queue
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from engine import auto, carpeta, vision
from server import CATALOGO

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salida_carpetas"
TOKENS_POR_CAPTURA = 3900  # entrada medida con Haiku; solo para avisar el costo
COLUMNAS = (("capture_id", "Captura", 120), ("decision_esperada", "Decisión", 120), ("motivo", "Motivo", 200),
            ("capture_store_name", "Tienda", 110), ("product_name", "Producto", 220),
            ("precio_detectado", "Precio", 70), ("precio_descuento", "Oferta", 70))


def fila(r):
    """Valores de una fila de la tabla a partir del registro."""
    motivo = r["motivo_rechazo"] or (r["reason_code"] if r["decision_esperada"] != "aprobada" else "")
    return tuple("" if r.get(k) is None else r.get(k) for k, _, _ in COLUMNAS[:2]) + (
        motivo, *("" if r.get(k) is None else r.get(k) for k, _, _ in COLUMNAS[3:]))


def salida_para(ruta):
    return SALIDA / (Path(ruta).name or "carpeta")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Validat3B · Analizar carpeta")
        self.geometry("1020x620")
        self.cola, self.registros, self.stop, self.hilo = queue.Queue(), {}, threading.Event(), None
        self.catalogo = auto.load_catalog(CATALOGO)
        hay_llave = "FOUNDRY_API_KEY" in os.environ

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.ruta = tk.StringVar()
        ttk.Label(top, text="Carpeta de fotos:").pack(side="left")
        ttk.Entry(top, textvariable=self.ruta).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Examinar…", command=self.examinar).pack(side="left")

        opc = ttk.Frame(self, padding=(8, 0))
        opc.pack(fill="x")
        self.usar_llm = tk.BooleanVar(value=hay_llave)
        self.reutilizar = tk.BooleanVar(value=True)
        self.workers = tk.IntVar(value=2)
        c = ttk.Checkbutton(opc, text="Usar Haiku (gasta tokens)", variable=self.usar_llm)
        c.pack(side="left")
        if not hay_llave:
            c.state(["disabled"])
            ttk.Label(opc, text="(define FOUNDRY_API_KEY para activarlo)").pack(side="left", padx=4)
        ttk.Checkbutton(opc, text="Reutilizar resultados guardados", variable=self.reutilizar).pack(side="left", padx=12)
        ttk.Label(opc, text="Simultáneas:").pack(side="left")
        ttk.Spinbox(opc, from_=1, to=4, width=3, textvariable=self.workers).pack(side="left", padx=4)

        acc = ttk.Frame(self, padding=8)
        acc.pack(fill="x")
        self.btn_analizar = ttk.Button(acc, text="Analizar carpeta", command=self.analizar)
        self.btn_analizar.pack(side="left")
        self.btn_detener = ttk.Button(acc, text="Detener", command=self.stop.set, state="disabled")
        self.btn_detener.pack(side="left", padx=6)
        ttk.Button(acc, text="Ver JSON", command=self.ver_json).pack(side="left")
        ttk.Button(acc, text="Abrir carpeta de resultados", command=self.abrir_salida).pack(side="left", padx=6)

        self.barra = ttk.Progressbar(self, mode="determinate")
        self.barra.pack(fill="x", padx=8)
        self.estado = tk.StringVar(value="Elige una carpeta con fotos <ID>_facade.jpg, <ID>_product.jpg y <ID>_shelf.jpg.")
        ttk.Label(self, textvariable=self.estado, padding=8).pack(fill="x")

        marco = ttk.Frame(self, padding=(8, 0, 8, 8))
        marco.pack(fill="both", expand=True)
        self.tabla = ttk.Treeview(marco, columns=[k for k, _, _ in COLUMNAS], show="headings")
        for k, titulo, ancho in COLUMNAS:
            self.tabla.heading(k, text=titulo)
            self.tabla.column(k, width=ancho, anchor="w")
        sb = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=sb.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tabla.bind("<Double-1>", lambda _e: self.ver_json())
        self.after(100, self.procesar_cola)

    def examinar(self):
        d = filedialog.askdirectory(title="Carpeta con fotos", initialdir=str(RAIZ.parent))
        if d:
            self.ruta.set(d)

    def analizar(self):
        """Pide confirmación (si gasta tokens) y arranca el análisis."""
        self.iniciar(self.ruta.get().strip(), self.usar_llm.get(), self.reutilizar.get(), confirmar=True)

    def iniciar(self, ruta, usar_llm, reutilizar, confirmar=False):
        if self.hilo and self.hilo.is_alive():
            return
        if not ruta or not Path(ruta).is_dir():
            return messagebox.showerror("Carpeta", "Elige una carpeta que exista.")
        capturas, avisos = carpeta.buscar_capturas(ruta)
        if not capturas:
            return messagebox.showwarning("Sin capturas", "No encontré grupos completos <ID>_facade/_product/_shelf.jpg.\n" + "\n".join(avisos[:8]))
        salida = salida_para(ruta)
        if confirmar and usar_llm and not messagebox.askokcancel(
                "Confirmar", f"Se analizarán {len(capturas)} capturas con Haiku (≈{len(capturas) * TOKENS_POR_CAPTURA // 1000}k tokens).\n"
                             f"Las fotos solo se envían al endpoint de Foundry del equipo.\n\nResultados en:\n{salida}"):
            return
        self.tabla.delete(*self.tabla.get_children())
        self.registros.clear()
        self.stop.clear()
        self.barra.configure(maximum=len(capturas), value=0)
        self.btn_analizar.state(["disabled"])
        self.btn_detener.state(["!disabled"])
        extra = f" · {len(avisos)} omitidas" if avisos else ""
        self.estado.set(f"Analizando {len(capturas)} capturas{extra}…")
        self.salida = salida
        try:
            client = vision.make_client() if usar_llm else None
        except Exception as e:  # noqa: BLE001
            self.fin()
            return messagebox.showerror("Haiku", f"No se pudo crear el cliente: {e}")
        # las variables de tkinter solo se leen en el hilo de la interfaz: aquí, no en el hilo de trabajo
        self.hilo = threading.Thread(target=self.trabajo, args=(ruta, salida, client, reutilizar, self.workers.get()), daemon=True)
        self.hilo.start()

    def trabajo(self, ruta, salida, client, reutilizar, workers):
        try:
            carpeta.analizar_carpeta(ruta, salida, client, self.catalogo, workers, reutilizar,
                                     on_result=lambda r, n, t: self.cola.put(("res", r, n, t)), stop=self.stop)
        except Exception as e:  # noqa: BLE001
            self.cola.put(("error", str(e)))
        self.cola.put(("fin",))

    def procesar_cola(self):
        """Pasa al hilo de la interfaz lo que producen los hilos de trabajo."""
        try:
            while True:
                m = self.cola.get_nowait()
                if m[0] == "res":
                    _, r, n, t = m
                    self.registros[r["capture_id"]] = r
                    self.tabla.insert("", "end", iid=r["capture_id"], values=fila(r))
                    self.barra.configure(value=n)
                    self.estado.set(f"Analizadas {n} de {t}…")
                elif m[0] == "error":
                    messagebox.showerror("Error", m[1])
                else:
                    self.fin()
        except queue.Empty:
            pass
        self.after(100, self.procesar_cola)

    def fin(self):
        c = Counter(r["decision_esperada"] for r in self.registros.values())
        detenido = " (detenido)" if self.stop.is_set() else ""
        self.estado.set(f"Listo{detenido}: {len(self.registros)} capturas · " +
                        " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(c.items())) +
                        f" · JSON en {getattr(self, 'salida', SALIDA)}")
        self.btn_analizar.state(["!disabled"])
        self.btn_detener.state(["disabled"])

    def ver_json(self):
        sel = self.tabla.selection()
        if not sel:
            return messagebox.showinfo("Ver JSON", "Selecciona una captura de la tabla.")
        ventana = tk.Toplevel(self)
        ventana.title(sel[0])
        ventana.geometry("640x700")
        texto = tk.Text(ventana, wrap="word", font=("Consolas", 10))
        texto.insert("1.0", json.dumps(self.registros[sel[0]], ensure_ascii=False, indent=2))
        texto.configure(state="disabled")
        texto.pack(fill="both", expand=True)

    def abrir_salida(self):
        d = getattr(self, "salida", SALIDA)
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(d)


if __name__ == "__main__":
    App().mainloop()
