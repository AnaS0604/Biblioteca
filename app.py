#!/usr/bin/env python3
"""Biblioteca UTP: Búsqueda binaria con Flask (con préstamos).

El algoritmo (elegir pasillo + búsqueda binaria) se ejecuta en Python.
El navegador pide el recorrido a /api/buscar y lo anima.
Los préstamos se guardan en el servidor, en el archivo prestamos.json.

Instalar:  pip install flask
Ejecutar:  python app_biblioteca_flask.py
"""
import json
import socket
import threading
import unicodedata
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# ---------------------------------------------------------------- datos
PAS = [("A", "E"), ("F", "J"), ("K", "O"), ("P", "T"), ("U", "Z")]
LIB = [
    ("Allende, Isabel", "La casa de los espíritus"), ("Asimov, Isaac", "Fundación"),
    ("Austen, Jane", "Orgullo y prejuicio"), ("Borges, Jorge Luis", "El Aleph"),
    ("Borges, Jorge Luis", "Ficciones"), ("Cervantes, Miguel de", "Don Quijote de la Mancha"),
    ("Dickens, Charles", "Grandes esperanzas"), ("Fuentes, Carlos", "La muerte de Artemio Cruz"),
    ("García Márquez, Gabriel", "Cien años de soledad"),
    ("García Márquez, Gabriel", "El amor en los tiempos del cólera"),
    ("Hugo, Victor", "Los miserables"), ("Huxley, Aldous", "Un mundo feliz"),
    ("Joyce, James", "Ulises"), ("Kafka, Franz", "La metamorfosis"),
    ("King, Stephen", "El resplandor"), ("Lorca, Federico García", "Bodas de sangre"),
    ("Mistral, Gabriela", "Desolación"), ("Murakami, Haruki", "Tokio blues"),
    ("Neruda, Pablo", "Veinte poemas de amor"), ("Orwell, George", "1984"),
    ("Paz, Octavio", "El laberinto de la soledad"), ("Poe, Edgar Allan", "El cuervo y otros cuentos"),
    ("Poniatowska, Elena", "La noche de Tlatelolco"), ("Rulfo, Juan", "Pedro Páramo"),
    ("Saramago, José", "Ensayo sobre la ceguera"), ("Tolkien, J. R. R.", "El señor de los anillos"),
    ("Unamuno, Miguel de", "Niebla"), ("Vargas Llosa, Mario", "La ciudad y los perros"),
    ("Verne, Julio", "Veinte mil leguas de viaje submarino"),
    ("Woolf, Virginia", "La señora Dalloway"), ("Zafón, Carlos Ruiz", "La sombra del viento"),
]


def norm(t):
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def pasillo_de(letra):
    for i, (a, b) in enumerate(PAS):
        if a.lower() <= letra <= b.lower():
            return i
    return None


# libros ordenados de la A a la Z y repartidos en su pasillo
ORDENADOS = sorted(LIB, key=lambda l: (norm(l[0]), norm(l[1])))
ESTANTES = [[l for l in ORDENADOS if pasillo_de(norm(l[0])[0]) == i] for i in range(len(PAS))]


# ------------------------------------------------------------ préstamos
ARCHIVO_PRESTAMOS = Path(__file__).with_name("prestamos.json")
_candado = threading.Lock()


def llave(libro):
    return f"{libro[0]}|{libro[1]}"


def cargar_prestamos():
    try:
        return set(json.loads(ARCHIVO_PRESTAMOS.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()


def guardar_prestamos(prestamos):
    try:
        ARCHIVO_PRESTAMOS.write_text(
            json.dumps(sorted(prestamos), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------ algoritmo
def buscar(v):
    """Devuelve el recorrido completo de la búsqueda (para que el navegador lo anime)."""
    v = v.strip()
    if not v:
        return {"ok": False, "error": "Escribe un apellido para buscar."}
    c = norm(v)
    letra = c[0]
    if not ("a" <= letra <= "z"):
        return {"ok": False, "error": "El apellido debe empezar con una letra de la A a la Z."}

    # 1) leer letreros hasta dar con el pasillo
    revisados, pasillo = [], None
    for i, (a, b) in enumerate(PAS):
        coincide = a.lower() <= letra <= b.lower()
        revisados.append({"i": i, "coincide": coincide})
        if coincide:
            pasillo = i
            break

    # 2) búsqueda binaria dentro del pasillo
    estante = ESTANTES[pasillo]
    claves = [norm(l[0]) for l in estante]
    lo, hi, cand, pasos = 0, len(estante) - 1, None, []
    while lo <= hi:
        mid = (lo + hi) // 2
        if claves[mid] < c:
            accion, nlo, nhi = "abajo", mid + 1, hi
        else:
            accion, nlo, nhi, cand = "arriba", lo, mid - 1, mid
        pasos.append({
            "paso": len(pasos) + 1, "lo": lo, "hi": hi, "mid": mid,
            "autor": estante[mid][0].split(",")[0], "accion": accion,
            "lo_nuevo": nlo, "hi_nuevo": nhi,
        })
        lo, hi = nlo, nhi

    # 3) todos los libros del mismo autor (quedan seguidos)
    encontrados = []
    if cand is not None and claves[cand].startswith(c):
        k = cand
        while k < len(estante) and claves[k].startswith(c):
            encontrados.append(k)
            k += 1

    prestamos = cargar_prestamos()
    return {
        "ok": True, "consulta": v, "letra": letra.upper(),
        "revisados": revisados, "pasillo": pasillo,
        "pasos": pasos, "encontrados": encontrados,
        "prestados": [llave(estante[k]) in prestamos for k in encontrados],
    }


# ------------------------------------------------------------------ API
@app.get("/api/datos")
def api_datos():
    return jsonify({"pasillos": PAS, "estanterias": ESTANTES})


@app.get("/api/buscar")
def api_buscar():
    r = buscar(request.args.get("q", ""))
    return jsonify(r), (200 if r["ok"] else 400)


@app.post("/api/prestamo")
def api_prestamo():
    d = request.get_json(silent=True) or {}
    clave = f"{d.get('autor', '')}|{d.get('titulo', '')}"
    if clave not in {llave(l) for l in LIB}:
        return jsonify({"ok": False, "error": "Ese libro no existe en la biblioteca."}), 404
    accion = d.get("accion")
    with _candado:
        prestamos = cargar_prestamos()
        if accion == "prestar":
            if clave in prestamos:
                return jsonify({"ok": False, "prestado": True,
                                "error": "Este libro está prestado. Espera a que lo devuelvan."}), 409
            prestamos.add(clave)
        elif accion == "devolver":
            if clave not in prestamos:
                return jsonify({"ok": False, "prestado": False,
                                "error": "Este libro no estaba prestado."}), 409
            prestamos.discard(clave)
        else:
            return jsonify({"ok": False, "error": "Acción no válida."}), 400
        guardar_prestamos(prestamos)
    return jsonify({"ok": True, "prestado": clave in prestamos})


@app.get("/")
def inicio():
    return Response(PAGINA, mimetype="text/html")


# ------------------------------------------------------------- página
PAGINA = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Biblioteca UTP: Búsqueda binaria (Flask)</title>
<style>
:root{
  box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px);
  --bg:#faf9f5;--card:#fff6d6;--neutral:#efece4;--line:#b4b2a9;--line2:#d3d1c7;--text:#2c2c2a;--muted:#73726c;--danger:#a32d2d;--accent:#8a5a1f;
  color-scheme:light;
}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){--bg:#1f1e1c;--card:#3a3426;--neutral:#34322e;--line:#6b6963;--line2:#4a4843;--text:#f1efe8;--muted:#a8a69e;--danger:#f09595;--accent:#e8b872;color-scheme:dark}
}
:root[data-theme="dark"]{--bg:#1f1e1c;--card:#3a3426;--neutral:#34322e;--line:#6b6963;--line2:#4a4843;--text:#f1efe8;--muted:#a8a69e;--danger:#f09595;--accent:#e8b872;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
main{max-width:860px;margin:0 auto;padding:20px 16px 32px}
.hero{text-align:center;padding:22px 16px 18px;margin-bottom:18px;border:1px solid var(--line2);border-radius:16px;background:linear-gradient(180deg,var(--card),var(--bg))}
.spines{width:min(300px,80%);height:auto;display:block;margin:0 auto 12px}
.welcome{margin:0;font-size:.85rem;letter-spacing:.28em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:Georgia,"Times New Roman",serif;font-size:clamp(2rem,7vw,3rem);line-height:1.15;margin:4px 0 8px;letter-spacing:.02em}
.divider{display:flex;align-items:center;gap:12px;max-width:340px;margin:6px auto 12px}
.divider span{flex:1;height:1px;background:var(--line)}
.divider i{width:8px;height:8px;background:var(--accent);transform:rotate(45deg)}
.sub{color:var(--muted);font-size:.95rem;margin:0 auto;max-width:560px}
.sub b{color:var(--accent)}
.ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:6px}
input[type=text]{font:inherit;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--neutral);color:var(--text);width:190px;max-width:100%}
button{font:inherit;padding:8px 18px;border:1px solid var(--line);border-radius:8px;background:var(--text);color:var(--bg);cursor:pointer;font-weight:600}
label{font-size:.85rem;color:var(--muted)}
#err{color:var(--danger);font-size:.85rem;min-height:20px}
.sv{border:1px solid var(--line2);border-radius:12px;background:var(--bg);overflow:hidden}
svg{display:block;width:100%;height:auto}
#msg{margin-top:10px;padding:12px 14px;border-radius:10px;background:var(--neutral);min-height:52px}
.leg{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:.85rem;color:var(--muted)}
.leg i{display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid #444441;vertical-align:-2px;margin-right:6px}
.how{margin-top:16px;font-size:.9rem;color:var(--muted)}
.how b{color:var(--text)}
.bk{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:10px;padding:12px 14px;border:1px solid var(--line2);border-radius:10px;background:var(--neutral)}
.au{font-size:.85rem;color:var(--muted)}
.st{font-size:.9rem;margin-top:4px}
.st.on{color:#3B6D11}
.st.off{color:var(--danger)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .st.on{color:#97C459}}
:root[data-theme="dark"] .st.on{color:#97C459}
button.alt{background:transparent;color:var(--text)}
button:disabled{opacity:.5;cursor:default}
</style>
</head>
<body>
<main>
  <header class="hero">
    <svg class="spines" viewBox="0 0 280 48" aria-hidden="true">
      <g stroke="#444441" stroke-width="0.6">
        <rect x="6" y="10" width="23" height="34" rx="2" fill="#D85A30"/>
        <rect x="35" y="16" width="23" height="28" rx="2" fill="#BA7517"/>
        <rect x="64" y="4" width="23" height="40" rx="2" fill="#639922"/>
        <rect x="93" y="14" width="23" height="30" rx="2" fill="#378ADD"/>
        <rect x="122" y="6" width="23" height="38" rx="2" fill="#7F77DD"/>
        <rect x="151" y="18" width="23" height="26" rx="2" fill="#D4537E"/>
        <rect x="180" y="8" width="23" height="36" rx="2" fill="#1D9E75"/>
        <rect x="209" y="12" width="23" height="32" rx="2" fill="#D85A30"/>
        <rect x="238" y="4" width="23" height="40" rx="2" fill="#378ADD"/>
      </g>
      <g fill="#FAC775">
        <rect x="9" y="16" width="17" height="3"/><rect x="38" y="22" width="17" height="3"/><rect x="67" y="10" width="17" height="3"/><rect x="96" y="20" width="17" height="3"/><rect x="125" y="12" width="17" height="3"/><rect x="154" y="24" width="17" height="3"/><rect x="183" y="14" width="17" height="3"/><rect x="212" y="18" width="17" height="3"/><rect x="241" y="10" width="17" height="3"/>
      </g>
      <rect x="0" y="44" width="280" height="4" rx="2" style="fill:var(--line)"/>
    </svg>
    <p class="welcome">Bienvenido a</p>
    <h1>Biblioteca UTP</h1>
    <div class="divider" aria-hidden="true"><span></span><i></i><span></span></div>
    <p class="sub">Algoritmo de <b>divide y vencerás</b> en <b>Python (Flask)</b> · primero se elige el pasillo por rango de letras y luego se busca a la mitad · <b>O(log n)</b></p>
  </header>
  <div class="ctl">
    <input type="text" id="q" value="Rulfo" placeholder="Apellido del autor" aria-label="Apellido del autor">
    <button id="go" disabled>Buscar</button>
    <label for="sp">Velocidad</label>
    <input type="range" id="sp" min="1" max="5" step="1" value="3" style="width:110px">
  </div>
  <div id="err" role="alert"></div>
  <div class="sv"><svg id="svg" viewBox="0 0 680 450" role="img" aria-label="Plano de la biblioteca con cinco pasillos y libros"></svg></div>
  <div id="msg" aria-live="polite">Cargando biblioteca…</div>
  <div id="res" aria-live="polite"></div>
  <div class="leg">
    <span><i style="background:#EF9F27"></i>Libro del medio (comparando)</span>
    <span><i style="background:#97C459"></i>Encontrado</span>
    <span><i style="background:var(--neutral)"></i>Descartado</span>
  </div>
  <p class="how"><b>Cómo funciona:</b> al pulsar Buscar, el navegador llama a <b>/api/buscar</b>; Flask elige el pasillo y hace la búsqueda binaria en Python, y devuelve cada paso. Después, si el libro está disponible puedes prestarlo, y si ya está prestado tendrás que esperar a que lo devuelvan. Los préstamos se guardan en el servidor (<b>prestamos.json</b>).</p>
</main>
<script>
var NS="http://www.w3.org/2000/svg";
var COV=["#D85A30","#BA7517","#639922","#378ADD","#7F77DD","#D4537E","#1D9E75"];
var SPN=["#993C1D","#854F0B","#3B6D11","#185FA5","#534AB7","#993556","#0F6E56"];
var Y0=64,RH=26,SW=114,WALK=310,DOORY=405,DOORX=340;
var PAS=[],ESTANTES=[],svg=document.getElementById("svg"),signs=[],shelves=[],rows=[],W,px=DOORX,py=DOORY,run=0,listo=false;
function x0(i){return 22+i*131;}
function gx(i){return x0(i)-11;}
function el(n,a,p){var e=document.createElementNS(NS,n);for(var k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;}
function txt(p,x,y,s,sz,w,anchor){var t=el("text",{x:x,y:y,"font-size":sz,"font-weight":w||400,"text-anchor":anchor||"start"},p);t.style.fill="var(--text)";t.textContent=s;return t;}
function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
function vel(){return Number(document.getElementById("sp").value);}
function pause(){return 1250-vel()*200;}
function msg(s){document.getElementById("msg").textContent=s;}
function mostrar(fl,found,prestados){
  var r=document.getElementById("res");r.innerHTML="";
  found.forEach(function(k,n){
    var l=fl[k].libro,prestado=!!prestados[n],box=document.createElement("div");box.className="bk";
    var info=document.createElement("div");
    var t=document.createElement("b");t.textContent=l[1];info.appendChild(t);
    var a=document.createElement("div");a.className="au";a.textContent=l[0];info.appendChild(a);
    var st=document.createElement("div");info.appendChild(st);
    var b=document.createElement("button");
    function estado(){
      b.style.display="";b.disabled=false;
      if(prestado){st.className="st off";st.textContent="Este libro está prestado. Espera a que lo devuelvan.";b.textContent="Devolver";b.className="alt";}
      else{st.className="st on";st.textContent="Disponible";b.textContent="Prestar";b.className="";}
    }
    b.onclick=async function(){
      b.disabled=true;
      try{
        var resp=await fetch("/api/prestamo",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({autor:l[0],titulo:l[1],accion:prestado?"devolver":"prestar"})});
        var d=await resp.json();
        if(!d.ok){if(typeof d.prestado==="boolean")prestado=d.prestado;estado();st.className="st off";st.textContent=d.error;return;}
        st.className="st on";
        st.textContent=prestado?"Libro devuelto. Gracias, ya está disponible para otra persona.":"¡Préstamo registrado! Disfruta tu lectura.";
        b.style.display="none";
      }catch(e){estado();st.className="st off";st.textContent="No se pudo conectar con el servidor.";}
    };
    estado();box.appendChild(info);box.appendChild(b);r.appendChild(box);
  });
}

function construir(){
  var wk=el("rect",{x:12,y:WALK-26,width:656,height:52,rx:4},svg);wk.style.fill="var(--neutral)";
  txt(svg,664,WALK+4,"pasillo central",11,400,"end").style.fill="var(--muted)";
  var dr=el("rect",{x:DOORX-34,y:432,width:68,height:10,rx:2},svg);dr.style.fill="var(--line)";
  txt(svg,DOORX,424,"ENTRADA",11,600,"middle");
  for(var i=0;i<PAS.length;i++){
    var x=x0(i);
    var s=el("rect",{x:x,y:8,width:SW,height:42,rx:4,"stroke-width":0.8},svg);s.style.fill="var(--card)";s.style.stroke="var(--line)";
    txt(svg,x+SW/2,25,"Pasillo "+(i+1),12,600,"middle");
    txt(svg,x+SW/2,43,PAS[i][0]+" – "+PAS[i][1],13,600,"middle");
    signs.push(s);
    var libs=ESTANTES[i];
    var sh=el("rect",{x:x-3,y:Y0-4,width:SW+6,height:libs.length*RH+8,rx:4,"stroke-width":0.8},svg);sh.style.fill="var(--neutral)";sh.style.stroke="var(--line)";
    shelves.push(sh);
    var fl=[];
    libs.forEach(function(l,k){
      var y=Y0+k*RH,h=RH-3,idx=(k+i)%COV.length;
      var cov=el("rect",{x:x,y:y,width:SW,height:h,rx:3,stroke:"#444441","stroke-width":0.5},svg);
      var spn=el("rect",{x:x,y:y,width:14,height:h,rx:3,stroke:"#444441","stroke-width":0.5},svg);
      var b1=el("line",{x1:x+4,y1:y+3,x2:x+4,y2:y+h-3,"stroke-width":1.5},svg);
      var b2=el("line",{x1:x+9,y1:y+3,x2:x+9,y2:y+h-3,"stroke-width":1.5},svg);
      var pg=el("rect",{x:x+17,y:y+3,width:SW-21,height:h-6,rx:1.5,stroke:"#B4B2A9","stroke-width":0.5},svg);
      var t=el("text",{x:x+22,y:y+h/2+4,"font-size":11},svg);t.textContent=l[0].split(",")[0];
      fl.push({c:cov,s:spn,b:[b1,b2],p:pg,t:t,y:y+h/2,idx:idx,libro:l});
    });
    rows.push(fl);
  }
  W=el("g",{},svg);W.style.transform="translate("+px+"px,"+py+"px)";
  el("ellipse",{cx:0,cy:0,rx:8,ry:11,fill:"#378ADD",stroke:"#0C447C","stroke-width":1.5},W);
  el("circle",{cx:0,cy:-15,r:6.5,fill:"#F5C4B3",stroke:"#712B13","stroke-width":1.5},W);
}

async function move(id,x,y){
  if(id!==run)return false;
  var d=Math.sqrt((x-px)*(x-px)+(y-py)*(y-py)),ms=Math.max(60,d/(100+vel()*110)*1000);
  W.style.transition="transform "+ms+"ms linear";W.style.transform="translate("+x+"px,"+y+"px)";
  px=x;py=y;await sleep(ms+30);return id===run;
}
function paint(i,lo,hi,mid,found){
  rows[i].forEach(function(f,k){
    var cv,sp,pg,bd,tc="#2C2C2A";
    if(found&&found.indexOf(k)>=0){cv="#97C459";sp="#3B6D11";pg="#EAF3DE";bd="#FAC775";}
    else if(k===mid){cv="#EF9F27";sp="#854F0B";pg="#FAEEDA";bd="#FAC775";}
    else if(k>=lo&&k<=hi){cv=COV[f.idx];sp=SPN[f.idx];pg="#FBF6E9";bd="#FAC775";}
    else{cv="var(--card)";sp="var(--line2)";pg="var(--neutral)";bd="var(--line)";tc="var(--muted)";}
    f.c.style.fill=cv;f.s.style.fill=sp;f.p.style.fill=pg;f.t.style.fill=tc;
    f.b.forEach(function(l){l.style.stroke=bd;});
  });
}
function reset(){
  for(var i=0;i<rows.length;i++){paint(i,0,rows[i].length-1);signs[i].style.fill="var(--card)";shelves[i].style.stroke="var(--line)";shelves[i].setAttribute("stroke-width","0.8");}
  W.style.transition="none";W.style.transform="translate("+DOORX+"px,"+DOORY+"px)";px=DOORX;py=DOORY;
}

async function search(){
  if(!listo)return;
  var v=document.getElementById("q").value.trim(),err=document.getElementById("err");
  var id=++run;
  var t;
  try{
    var r=await fetch("/api/buscar?q="+encodeURIComponent(v));
    t=await r.json();
  }catch(e){err.textContent="No se pudo conectar con el servidor Flask.";return;}
  if(id!==run)return;
  if(!t.ok){err.textContent=t.error;return;}
  err.textContent="";
  reset();document.getElementById("res").innerHTML="";await sleep(60);
  msg("Buscas «"+t.consulta+"». Entras a la biblioteca y lees los letreros…");
  if(!await move(id,DOORX,WALK))return; await sleep(pause());

  // 1) letreros (el servidor ya decidió cuáles se revisan)
  for(var n=0;n<t.revisados.length;n++){
    var rv=t.revisados[n],i=rv.i,rango=PAS[i][0]+"–"+PAS[i][1];
    if(!await move(id,gx(i),WALK))return;
    if(rv.coincide){signs[i].style.fill="#97C459";msg("Pasillo "+(i+1)+" ("+rango+"): «"+t.consulta+"» empieza con «"+t.letra+"». ¡Es este pasillo!");await sleep(pause());break;}
    signs[i].style.fill="#F09595";msg("Pasillo "+(i+1)+" ("+rango+"): «"+t.letra+"» no está en este rango. Sigo…");
    await sleep(pause());if(id!==run)return;
  }

  // 2) búsqueda binaria (cada paso viene calculado por Python)
  var p=t.pasillo,fl=rows[p];
  shelves[p].style.stroke="#3B6D11";shelves[p].setAttribute("stroke-width","2");
  msg("Entro al pasillo "+(p+1)+". Sus libros están de la A a la Z: uso búsqueda binaria.");
  if(!await move(id,gx(p),fl[Math.floor(fl.length/2)].y))return;await sleep(pause());
  for(var s=0;s<t.pasos.length;s++){
    var st=t.pasos[s];
    if(!await move(id,gx(p),fl[st.mid].y))return;
    paint(p,st.lo,st.hi,st.mid);
    if(st.accion==="abajo")msg("Paso "+st.paso+": miro «"+st.autor+"». Va ANTES que «"+t.consulta+"» → descarto lo de arriba y busco más abajo.");
    else msg("Paso "+st.paso+": miro «"+st.autor+"». Va IGUAL o DESPUÉS que «"+t.consulta+"» → descarto lo de abajo y busco más arriba.");
    await sleep(pause());
    if(id!==run)return;paint(p,st.lo_nuevo,st.hi_nuevo);await sleep(250);
  }

  // 3) resultado
  var total=t.pasos.length,found=t.encontrados;
  if(!found.length){paint(p,1,0);msg("No tenemos libros de «"+t.consulta+"» en el pasillo "+(p+1)+" (la búsqueda terminó en "+total+" pasos).");return;}
  if(!await move(id,gx(p),fl[found[0]].y))return;
  for(var d=0;d<6;d++){paint(p,1,0,null,d%2===0?found:[]);await sleep(170);if(id!==run)return;}
  paint(p,1,0,null,found);
  msg("¡Encontrado en "+total+" pasos dentro del pasillo "+(p+1)+"! "+fl[found[0]].libro[0]+": "+found.map(function(k){return "«"+fl[k].libro[1]+"»";}).join("; "));
  mostrar(fl,found,t.prestados);
}

document.getElementById("go").onclick=search;
document.getElementById("q").onkeydown=function(e){if(e.key==="Enter")search();};
document.getElementById("q").oninput=function(){document.getElementById("err").textContent="";};

fetch("/api/datos").then(function(r){return r.json();}).then(function(d){
  PAS=d.pasillos;ESTANTES=d.estanterias;construir();reset();
  listo=true;document.getElementById("go").disabled=false;
  msg("Escribe un apellido y pulsa Buscar.");
}).catch(function(){msg("No se pudo cargar la biblioteca desde el servidor.");});
</script>
</body>
</html>
'''


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    puerto = puerto_libre()
    url = f"http://127.0.0.1:{puerto}"
    print(f"Servidor Flask listo en {url}  (Ctrl+C para detener)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=puerto, debug=False)
