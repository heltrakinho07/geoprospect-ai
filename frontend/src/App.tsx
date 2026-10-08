import {useEffect,useRef,useState} from "react";
import maplibregl from "maplibre-gl";
import {bbox} from "@turf/turf";
import {api} from "./api";
import RasterPanel,{type RasterOverlay} from "./RasterPanel";
import {Activity,ArrowRight,ChevronDown,Cloud,Database,Download,FileJson,FolderOpen,Layers3,LogOut,MapPinned,Menu,Plus,Satellite,ShieldCheck,Target,Trash2,Upload,Waypoints,X} from "lucide-react";

type GeoData={type:string;coordinates?:unknown;features?:unknown[];geometry?:GeoData};
type Project={id:string;organization_id:string;name:string;target_mineral:string|null;aoi_geojson:GeoData;created_at:string};
type Dataset={id:string;name:string;geojson:GeoData;feature_count:number};
type StacItem={id:string;datetime?:string;cloud_cover?:number;collection?:string;bbox?:number[]};
type AuthResponse={access_token:string;organization?:{id:string;name:string}};
type Membership={id:string;name:string;role:string};
type MyInfo={organizations:Membership[]};

const makeEmpty=()=>({type:"FeatureCollection",features:[] as unknown[]});
const apiPath=(oid:string)=>"/v1/orgs/"+encodeURIComponent(oid);
const validRegion=(input:any):GeoData=>{
  const geometry=input?.type==="Feature"?input.geometry:input?.type==="FeatureCollection"?input.features?.[0]?.geometry:input;
  if(!geometry || !["Polygon","MultiPolygon"].includes(geometry.type))throw new Error("A área deve ser um Polygon ou MultiPolygon GeoJSON");
  return geometry;
};
function setSource(map:maplibregl.Map,id:string,feature:any){
  const source=map.getSource(id) as maplibregl.GeoJSONSource|undefined;
  if(source)source.setData(feature);
}
const polygon=(pts:number[][]):any=>pts.length>=3?{type:"Feature",properties:{},geometry:{type:"Polygon",coordinates:[[...pts,pts[0]]]}}:makeEmpty();
const fc=(g:GeoData):any=>({type:"FeatureCollection",features:[{type:"Feature",properties:{},geometry:g}]});

function Login({onLogin}:{onLogin:(a:AuthResponse)=>void}){
  const [mode,setMode]=useState<"register"|"login">("register"),[email,setEmail]=useState(""),[password,setPassword]=useState(""),[company,setCompany]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const submit=async(e:React.FormEvent)=>{
    e.preventDefault();setBusy(true);setError("");
    try{
      const payload=mode==="register"?{email,password,organization_name:company}:{email,password};
      const response=await api<AuthResponse>("/v1/auth/"+(mode==="register"?"register":"login"),{method:"POST",body:JSON.stringify(payload)});
      onLogin(response);
    }catch(e){setError(e instanceof Error?e.message:"Falha ao autenticar");}finally{setBusy(false);}
  };
  return <main className="login-page"><div className="auth-side">
    <div className="brand"><span className="brand-icon"><Waypoints size={20}/></span><span>GEOPROSPECT <b>AI</b></span></div>
    <div className="auth-head"><span className="eyebrow"><span className="dot"/> MINERAL EXPLORATION INTELLIGENCE</span><h1>Transforme dados geológicos em <em>decisões melhores.</em></h1><p>Organize áreas de exploração, integre camadas, consulte imagens Sentinel-2 e prepare a selecção de alvos num único ambiente.</p></div>
    <div className="auth-foot">Um produto GEOLÍTHICA <span>•</span> Versão de desenvolvimento R0/R1</div>
  </div><div className="auth-form-wrap"><form className="auth-card" onSubmit={submit}>
    <span className="pill"><ShieldCheck size={14}/> Área de trabalho privada</span><h2>{mode==="register"?"Criar espaço de trabalho":"Entrar na plataforma"}</h2><p>{mode==="register"?"Comece por registar a sua organização.":"Aceda aos projectos da sua organização."}</p>
    {mode==="register"&&<label>Organização<input required minLength={2} maxLength={160} placeholder="Nome da empresa" value={company} onChange={e=>setCompany(e.target.value)}/></label>}
    <label>E-mail<input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="nome@empresa.com"/></label>
    <label>Palavra-passe<input required type="password" minLength={mode==="register"?12:1} autoComplete={mode==="register"?"new-password":"current-password"} value={password} onChange={e=>setPassword(e.target.value)} placeholder="Mínimo de 12 caracteres"/></label>
    {error&&<div className="error">{error}</div>}
    <button className="primary" disabled={busy}>{busy?"A processar...":mode==="register"?"Criar organização":"Entrar"}<ArrowRight size={16}/></button>
    <p className="auth-switch">{mode==="register"?"Já tem uma conta?":"Ainda não tem conta?"} <button type="button" className="link" onClick={()=>{setMode(mode==="register"?"login":"register");setError("");}}>{mode==="register"?"Iniciar sessão":"Criar conta"}</button></p>
  </form></div></main>;
}

export default function App(){
  const [token,setToken]=useState(()=>sessionStorage.getItem("gp_token")||"");
  const [orgs,setOrgs]=useState<Membership[]>([]);
  const [orgId,setOrgId]=useState("");
  const [panel,setPanel]=useState<"projects"|"layers"|"sentinel"|"raster">("projects");
  const [projects,setProjects]=useState<Project[]>([]);
  const [project,setProject]=useState<Project|null>(null);
  const [datasets,setDatasets]=useState<Dataset[]>([]);
  const [scenes,setScenes]=useState<StacItem[]>([]);
  const [rasterOverlay,setRasterOverlay]=useState<RasterOverlay|null>(null);
  const [draw,setDraw]=useState(false);
  const drawRef=useRef(false);
  const [vertices,setVertices]=useState<number[][]>([]);
  const [projectName,setProjectName]=useState("");
  const [mineral,setMineral]=useState("Ouro");
  const [createOpen,setCreateOpen]=useState(false);
  const [dateFrom,setDateFrom]=useState("2025-01-01"),[dateTo,setDateTo]=useState("2025-02-01"),[clouds,setClouds]=useState(25);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [mobileNav,setMobileNav]=useState(false),[mapReady,setMapReady]=useState(false);
  const mapHolder=useRef<HTMLDivElement|null>(null);
  const map=useRef<maplibregl.Map|null>(null);
  const pickArea=useRef<HTMLInputElement|null>(null);
  const pickDataset=useRef<HTMLInputElement|null>(null);

  useEffect(()=>{
    const m=map.current;
    if(!m||!mapReady||!rasterOverlay)return;
    const [west,south,east,north]=rasterOverlay.bounds;
    // Georeferenced image overlay; source is a protected blob URL fetched using bearer auth.
    const render=()=>{
      if(m.getLayer("processed-raster"))m.removeLayer("processed-raster");
      if(m.getSource("processed-raster"))m.removeSource("processed-raster");
      m.addSource("processed-raster",{type:"image",url:rasterOverlay.url,
        coordinates:[[west,north],[east,north],[east,south],[west,south]]});
      m.addLayer({id:"processed-raster",type:"raster",source:"processed-raster",
        paint:{"raster-opacity":0.82}},m.getLayer("project-outline")?"project-outline":undefined);
    };
    if(m.isStyleLoaded())render();else m.once("load",render);
    return ()=>{
      if(m.getLayer("processed-raster"))m.removeLayer("processed-raster");
      if(m.getSource("processed-raster"))m.removeSource("processed-raster");
      URL.revokeObjectURL(rasterOverlay.url);
    };
  },[rasterOverlay,mapReady]);
  useEffect(()=>{setRasterOverlay(null);},[orgId,project?.id]);
  useEffect(()=>{drawRef.current=draw;},[draw]);
  useEffect(()=>{
    if(!token){setOrgs([]);setOrgId("");return;}
    api<MyInfo>("/v1/me",{},token).then(r=>{setOrgs(r.organizations);setOrgId(o=>r.organizations.some(n=>n.id===o)?o:r.organizations[0]?.id||"");}).catch(()=>{setToken("");sessionStorage.removeItem("gp_token");});
  },[token]);
  useEffect(()=>{
    if(!token||!orgId)return;
    setProject(null);setDatasets([]);setScenes([]);
    api<Project[]>(apiPath(orgId)+"/projects",{},token).then(setProjects).catch(e=>setError(String(e)));
  },[token,orgId]);
  useEffect(()=>{
    if(!project || !token || !orgId){setDatasets([]);return;}
    api<Dataset[]>(apiPath(orgId)+"/projects/"+encodeURIComponent(project.id)+"/datasets",{},token).then(setDatasets).catch(e=>setError(String(e)));
  },[project,token,orgId]);
  useEffect(()=>{
    if(!orgId||!mapHolder.current)return;
    const m=new maplibregl.Map({
      container:mapHolder.current,center:[33,-19],zoom:5,
      style:{version:8,sources:{osm:{type:"raster",tiles:["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],tileSize:256,attribution:"© OpenStreetMap contributors"}},layers:[{id:"osm",source:"osm",type:"raster"}]}
    });
    map.current=m;m.addControl(new maplibregl.NavigationControl(),"top-right");
    m.on("load",()=>{
      for(const id of ["project-area","uploaded-data","drawing"])m.addSource(id,{type:"geojson",data:makeEmpty() as any});
      m.addLayer({id:"project-fill",type:"fill",source:"project-area",paint:{"fill-color":"#22b7a0","fill-opacity":0.16}});
      m.addLayer({id:"project-outline",type:"line",source:"project-area",paint:{"line-color":"#45dfc1","line-width":3}});
      m.addLayer({id:"uploaded-fill",type:"fill",source:"uploaded-data",paint:{"fill-color":"#ebb456","fill-opacity":0.3}});
      m.addLayer({id:"uploaded-lines",type:"line",source:"uploaded-data",paint:{"line-color":"#f2c46d","line-width":2}});
      m.addLayer({id:"uploaded-points",type:"circle",source:"uploaded-data",paint:{"circle-color":"#f2c46d","circle-radius":6,"circle-stroke-width":2,"circle-stroke-color":"#142734"}});
      m.addLayer({id:"draw-fill",type:"fill",source:"drawing",paint:{"fill-color":"#34ddba","fill-opacity":0.19}});
      m.addLayer({id:"draw-outline",type:"line",source:"drawing",paint:{"line-color":"#34ddba","line-width":3,"line-dasharray":[2,1]}});
      setMapReady(true);
    });
    m.on("click",e=>{if(drawRef.current)setVertices(old=>[...old,[e.lngLat.lng,e.lngLat.lat]]);});
    return ()=>{setMapReady(false);map.current=null;m.remove();};
  },[orgId]);
  useEffect(()=>{
    const m=map.current;if(!m||!mapReady)return;
    setSource(m,"project-area",project?fc(project.aoi_geojson):makeEmpty());
    const all=datasets.flatMap(d=>Array.isArray(d.geojson.features)?d.geojson.features:[]);
    setSource(m,"uploaded-data",{type:"FeatureCollection",features:all});
    if(project){
      try{const bounds=bbox(project.aoi_geojson as any);m.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]],{padding:55,maxZoom:11,duration:500});}catch{/* geometry already validated on API */}
    }
  },[project,datasets,mapReady]);
  useEffect(()=>{if(mapReady&&map.current)setSource(map.current,"drawing",polygon(vertices));},[vertices,mapReady]);
  function login(a:AuthResponse){sessionStorage.setItem("gp_token",a.access_token);setToken(a.access_token);if(a.organization)setOrgId(a.organization.id);}
  function logout(){sessionStorage.removeItem("gp_token");setToken("");setProject(null);setProjects([]);setError("");}
  function resetMessages(){setError("");setNotice("");}
  async function createProject(){
    if(!orgId||!projectName.trim()||vertices.length<3){setError("Defina um nome e uma área com pelo menos 3 vértices.");return;}
    setBusy(true);resetMessages();
    try{
      const result=await api<Project>(apiPath(orgId)+"/projects",{method:"POST",body:JSON.stringify({name:projectName,target_mineral:mineral,aoi_geojson:polygon(vertices).geometry})},token);
      setProjects(old=>[result,...old]);setProject(result);setDraw(false);setVertices([]);setCreateOpen(false);setProjectName("");setNotice("Projecto criado com sucesso.");
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function loadArea(file:File){
    resetMessages();
    try{
      const json=JSON.parse(await file.text());const geom=validRegion(json);
      if(geom.type!=="Polygon")throw new Error("Para o desenho inicial carregue um GeoJSON Polygon; MultiPolygon pode ser usado via API.");
      setVertices((geom.coordinates as number[][][])[0].slice(0,-1));setCreateOpen(true);setDraw(false);setNotice("Área importada. Configure o projecto e guarde.");
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  }
  async function uploadDataset(file:File){
    if(!project)return;
    setBusy(true);resetMessages();
    try{
      const geojson=JSON.parse(await file.text());
      const added=await api<Dataset>(apiPath(orgId)+"/projects/"+project.id+"/datasets",{method:"POST",body:JSON.stringify({name:file.name,geojson})},token);
      setDatasets(old=>[...old,{...added,geojson}]);setNotice("Camada importada com "+added.feature_count+" feições.");
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function searchSentinel(){
    if(!project)return;
    setBusy(true);resetMessages();
    try{
      const result=await api<{items:StacItem[]}>(apiPath(orgId)+"/stac/search",{method:"POST",body:JSON.stringify({project_id:project.id,date_from:dateFrom,date_to:dateTo,max_cloud:clouds,limit:20})},token);
      setScenes(result.items);setNotice("Pesquisa concluída: "+result.items.length+" cenas. Estes são metadados; não são análises espectrais.");
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  function downloadProject(){
    if(!project)return;
    const blob=new Blob([JSON.stringify({project, datasets},null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="geoprospect-"+project.id+".json";a.click();URL.revokeObjectURL(url);
  }
  if(!token)return <Login onLogin={login}/>;
  return <div className="workspace">
    <aside className={"side "+(mobileNav?"side-open":"")}>
      <div className="brand side-brand"><span className="brand-icon"><Waypoints size={19}/></span><span>GEOPROSPECT <b>AI</b></span><button className="mobile-close icon-button" onClick={()=>setMobileNav(false)} aria-label="Fechar navegação"><X size={18}/></button></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="nav">
        <button className={panel==="projects"?"active":""} onClick={()=>{setPanel("projects");setMobileNav(false);}}><FolderOpen size={17}/> Projectos <ArrowRight size={14} className="nav-arrow"/></button>
        <button className={panel==="layers"?"active":""} onClick={()=>{setPanel("layers");setMobileNav(false);}}><Layers3 size={17}/> Camadas</button>
        <button className={panel==="sentinel"?"active":""} onClick={()=>{setPanel("sentinel");setMobileNav(false);}}><Satellite size={17}/> Sentinel Explorer</button>
        <button className={panel==="raster"?"active":""} onClick={()=>{setPanel("raster");setMobileNav(false);}}><Cloud size={17}/> Índices espectrais</button>
        <button disabled title="Disponível na fase R3"><Target size={17}/> Prospectivity Engine <span className="soon">R3</span></button>
      </nav>
      <div className="side-bottom"><div className="edition">R2 <span>Sentinel Hub pilot</span></div><button onClick={logout}><LogOut size={16}/> Sair</button></div>
    </aside>
    <div className="main">
      <header className="topbar"><button className="mobile-menu icon-button" aria-label="Navegação" onClick={()=>setMobileNav(true)}><Menu/></button><div className="breadcrumb">Exploration Workspace <span>/</span> {project?.name||"Todos os projectos"}</div><div className="top-actions"><select aria-label="Organização" value={orgId} onChange={e=>setOrgId(e.target.value)}>{orgs.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select><span className="top-avatar">GP</span></div></header>
      <div className="content">
        <section className="explorer-panel">
          <div className="panel-header"><span className="eyebrow">{panel==="projects"?"EXPLORATION PROJECTS":panel==="layers"?"GEOSPATIAL DATA":panel==="raster"?"SPECTRAL PROCESSING":"EARTH OBSERVATION"}</span><h2>{panel==="projects"?"Projectos":panel==="layers"?"Camadas":panel==="raster"?"Índices espectrais":"Sentinel Explorer"}</h2><p>{panel==="projects"?"Organize os seus estudos de prospecção.":panel==="layers"?"Importe dados vectoriais para análise.":panel==="raster"?"Processar Sentinel-2 e guardar GeoTIFF.":"Consulte cenas Sentinel-2 L2A do Copernicus."}</p></div>
          {error&&<div role="alert" className="error">{error}<button onClick={()=>setError("")} aria-label="Fechar"><X size={14}/></button></div>}
          {notice&&<div className="notice">{notice}<button onClick={()=>setNotice("")} aria-label="Fechar"><X size={14}/></button></div>}
          {panel==="projects"&&<div className="panel-body">
            <button className="primary" onClick={()=>{setCreateOpen(true);resetMessages();}}><Plus size={16}/> Novo projecto</button>
            <div className="list-label">PROJECTOS ({projects.length})</div>
            {projects.length===0&&<div className="empty"><FolderOpen size={28}/><strong>Nenhum projecto ainda</strong><p>Crie uma área de estudo para começar.</p></div>}
            {projects.map(p=><button key={p.id} className={"project-row "+(project?.id===p.id?"selected":"")} onClick={()=>{setProject(p);setVertices([]);setCreateOpen(false);}}><div className="project-icon"><MapPinned size={17}/></div><span><b>{p.name}</b><small>{p.target_mineral||"Exploração mineral"}</small></span><ArrowRight size={15}/></button>)}
            {project&&<button className="secondary" onClick={downloadProject}><Download size={15}/> Exportar projecto (JSON)</button>}
          </div>}
          {panel==="layers"&&<div className="panel-body">
            {!project?<div className="empty"><Layers3 size={27}/><p>Seleccione um projecto primeiro.</p><button className="secondary" onClick={()=>setPanel("projects")}>Escolher projecto</button></div>:<>
              <button className="primary" onClick={()=>pickDataset.current?.click()} disabled={busy}><Upload size={16}/> Importar GeoJSON</button>
              <input hidden ref={pickDataset} type="file" accept=".json,.geojson,application/geo+json" onChange={e=>{const f=e.target.files?.[0];if(f)void uploadDataset(f);e.target.value="";}}/>
              <div className="list-label">CAMADAS DO PROJECTO ({datasets.length})</div>
              {datasets.map(d=><div className="layer-row" key={d.id}><FileJson size={17}/><div><b>{d.name}</b><small>{d.feature_count} feições</small></div></div>)}
              {!datasets.length&&<div className="empty"><Database size={27}/><p>Nenhuma camada carregada.</p></div>}
            </>}
          </div>}
          {panel==="raster"&&(project?<RasterPanel key={project.id+"-"+orgId} orgId={orgId} projectId={project.id} token={token} onPreview={setRasterOverlay}/>:<div className="panel-body"><div className="empty">Seleccione um projecto para processar imagens Sentinel-2.</div></div>)}
          {panel==="sentinel"&&<div className="panel-body">
            {!project?<div className="empty"><Satellite size={27}/><p>Seleccione um projecto para pesquisar imagens na sua área.</p></div>:<>
              <label className="field">Data inicial<input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/></label>
              <label className="field">Data final<input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/></label>
              <label className="field">Nuvens máximas: {clouds}%<input type="range" min={0} max={100} step={5} value={clouds} onChange={e=>setClouds(Number(e.target.value))}/></label>
              <button className="primary" onClick={()=>void searchSentinel()} disabled={busy}><Cloud size={16}/>{busy?"A pesquisar...":"Pesquisar cenas"}</button>
              <div className="list-label">CENAS ENCONTRADAS ({scenes.length})</div>
              {scenes.map((s,i)=><div className="scene-row" key={s.id||i}><Satellite size={16}/><div><b>{s.datetime?.slice(0,10)||"Sem data"}</b><small>{s.id?.slice(0,38)} · {s.cloud_cover??"?"}% nuvens</small></div></div>)}
              <p className="disclaimer">O catálogo apresenta metadados de cenas; utilize a secção Índices espectrais para processar rasters no servidor.</p>
            </>}
          </div>}
        </section>
        <section className="map-area"><div ref={mapHolder} className="map-container"/><div className="map-label"><span className="dot"/> MAPA 2D · PROJECTO INDEPENDENTE</div>
          <div className="map-bottom"><span><Activity size={14}/> WebGIS · EPSG:4326</span><span>{project?"Área: "+project.name:"Moçambique • Mundo"}</span></div>
          {createOpen&&<div className="create-panel">
            <div className="create-header"><div><span className="eyebrow">NOVO ESTUDO</span><h3>Criar projecto</h3></div><button className="icon-button" aria-label="Fechar" onClick={()=>{setCreateOpen(false);setDraw(false);}}><X size={18}/></button></div>
            <label className="field">Nome do projecto<input maxLength={200} placeholder="Ex.: Prospecção Manica 2026" value={projectName} onChange={e=>setProjectName(e.target.value)}/></label>
            <label className="field">Mineral alvo<select value={mineral} onChange={e=>setMineral(e.target.value)}><option>Ouro</option><option>Cobre</option><option>Lítio</option><option>Grafite</option><option>Outros</option></select></label>
            <div className="two-buttons"><button className={"secondary "+(draw?"chosen":"")} onClick={()=>setDraw(v=>!v)}><MapPinned size={15}/>{draw?"A desenhar...":"Desenhar AOI"}</button><button className="secondary" onClick={()=>pickArea.current?.click()}><Upload size={15}/> Carregar GeoJSON</button></div>
            <input hidden ref={pickArea} type="file" accept=".geojson,.json" onChange={e=>{const f=e.target.files?.[0];if(f)void loadArea(f);e.target.value="";}}/>
            <p className="hint">{draw?"Clique no mapa para colocar os vértices.":"A área de estudo deve ter pelo menos 3 vértices."} <b>{vertices.length} vértices</b></p>
            <div className="two-buttons"><button className="secondary" onClick={()=>setVertices([])}><Trash2 size={14}/> Limpar</button><button className="primary" disabled={busy||vertices.length<3||projectName.trim().length<3} onClick={()=>void createProject()}>{busy?"A guardar...":"Guardar projecto"}<ArrowRight size={15}/></button></div>
          </div>}
        </section>
      </div>
    </div>
  </div>;
}
