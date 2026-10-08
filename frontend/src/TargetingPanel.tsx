import {useCallback,useEffect,useMemo,useState} from "react";
import {api,API_URL} from "./api";
import {CloudDownload,Eye,Play,RefreshCw,Target} from "lucide-react";
import type {RasterOverlay} from "./RasterPanel";

type Dataset={id:string;name:string;geojson:{type:string;features?:any[]};feature_count:number};
type RasterJob={id:string;index:string;status:string;stats?:{valid_fraction:number};created_at:string};
type TargetRun={
  id:string;status:string;created_at:string;error?:string;
  config:{raster_job_id:string;target_threshold:number};
  stats?:{mean:number;max:number;valid_fraction:number;targets:number;bounds:number[];
    inputs:string[];weights_normalized:Record<string,number>;metric_crs:string;sensitivity?:{scenarios:number;max_threshold_flip_fraction:number;relative_perturbation:number}};
};
type FeatureCollection={type:"FeatureCollection";features:any[]};
type Props={
  orgId:string;projectId:string;token:string;datasets:Dataset[];
  onPreview:(overlay:RasterOverlay)=>void;onTargets:(geojson:FeatureCollection)=>void;
};
const emptyTargets=():FeatureCollection=>({type:"FeatureCollection",features:[]});
const path=(org:string,pid:string)=>"/v1/orgs/"+encodeURIComponent(org)+"/projects/"+encodeURIComponent(pid);
const getTypes=(d:Dataset)=>new Set((d.geojson.features||[]).map(f=>f?.geometry?.type).filter(Boolean));
const hasType=(d:Dataset, types:string[])=>Array.from(getTypes(d)).some(t=>types.includes(t));

export default function TargetingPanel({orgId,projectId,token,datasets,onPreview,onTargets}:Props){
  const base=path(orgId,projectId);
  const url=base+"/prospectivity";
  const [rasters,setRasters]=useState<RasterJob[]>([]);
  const [runs,setRuns]=useState<TargetRun[]>([]);
  const [rasterId,setRasterId]=useState("");
  const [minimum,setMinimum]=useState("-1"),[maximum,setMaximum]=useState("1");
  const [invert,setInvert]=useState(false),[spectralWeight,setSpectralWeight]=useState("1");
  const [faultId,setFaultId]=useState("");
  const [faultWeight,setFaultWeight]=useState("1"),[distanceKm,setDistanceKm]=useState("3");
  const [geologyId,setGeologyId]=useState("");
  const [geologyWeight,setGeologyWeight]=useState("1"),[lithologyField,setLithologyField]=useState("unit");
  const [favorable,setFavorable]=useState("");
  const [threshold,setThreshold]=useState("0.7"),[minPixels,setMinPixels]=useState("5");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const faults=useMemo(()=>datasets.filter(d=>hasType(d,["LineString","MultiLineString"])),[datasets]);
  const lithologies=useMemo(()=>datasets.filter(d=>hasType(d,["Polygon","MultiPolygon"])),[datasets]);
  const refresh=useCallback(async()=>{
    const [r,j]=await Promise.all([
      api<TargetRun[]>(url+"/runs",{},token),
      api<RasterJob[]>(base+"/raster/jobs",{},token)
    ]);
    setRuns(r);
    const completed=j.filter(x=>x.status==="completed");
    setRasters(completed);
    setRasterId(current=>completed.some(x=>x.id===current)?current:completed[0]?.id||"");
  },[url,base,token]);
  useEffect(()=>{
    let active=true;
    refresh().catch(e=>{if(active)setError(String(e));});
    const timer=setInterval(()=>refresh().catch(()=>{}),6000);
    return ()=>{active=false;clearInterval(timer);};
  },[refresh]);
  const activeRaster=rasters.find(r=>r.id===rasterId);
  useEffect(()=>{
    if(!activeRaster)return;
    if(["ndvi","ndwi","ndmi"].includes(activeRaster.index)){
      setMinimum("-1");setMaximum("1");
    }else{setMinimum("0");setMaximum("3");}
  },[activeRaster?.id]);

  async function submit(){
    setBusy(true);setError("");setNotice("");
    try{
      if(!rasterId)throw new Error("É necessário concluir uma análise raster antes do modelo de prospectividade.");
      const body={
        raster_job_id:rasterId,
        spectral_min:Number(minimum),spectral_max:Number(maximum),
        spectral_invert:invert,spectral_weight:Number(spectralWeight),
        structural_dataset_id:faultId||null,
        structural_weight:faultId?Number(faultWeight):0,
        fault_distance_km:Number(distanceKm),
        geology_dataset_id:geologyId||null,
        geology_weight:geologyId?Number(geologyWeight):0,
        lithology_field:lithologyField,
        favorable_values:geologyId?favorable.split(",").map(v=>v.trim()).filter(Boolean):[],
        target_threshold:Number(threshold),min_target_pixels:Number(minPixels)
      };
      if(!Number.isFinite(body.spectral_min)||!Number.isFinite(body.spectral_max))throw new Error("Intervalos espectrais inválidos.");
      await api<TargetRun>(url+"/runs",{method:"POST",body:JSON.stringify(body)},token);
      setNotice("Modelo submetido; o resultado surgirá no histórico.");
      await refresh();
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function fetchProtected(id:string,kind:"preview"|"geotiff"|"targets"|"provenance"|"sensitivity"):Promise<Blob>{
    const response=await fetch(API_URL+url+"/runs/"+id+"/"+kind,{headers:{"Authorization":"Bearer "+token}});
    if(!response.ok)throw new Error("Não foi possível obter o resultado ("+response.status+").");
    return response.blob();
  }
  async function view(run:TargetRun){
    setBusy(true);setError("");setNotice("");
    try{
      if(!run.stats?.bounds)throw new Error("O resultado não tem extensão espacial.");
      const [image,features]=await Promise.all([fetchProtected(run.id,"preview"),fetchProtected(run.id,"targets")]);
      const geojson=JSON.parse(await features.text()) as FeatureCollection;
      if(geojson?.type!=="FeatureCollection")throw new Error("Resultados vectoriais inválidos.");
      onTargets(geojson);
      onPreview({url:URL.createObjectURL(image),bounds:run.stats.bounds});
      setNotice(geojson.features.length+" polígonos candidatos desenhados no mapa.");
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function download(run:TargetRun,kind:"geotiff"|"targets"|"provenance"|"sensitivity"){
    setBusy(true);setError("");
    try{
      const content=await fetchProtected(run.id,kind);
      const address=URL.createObjectURL(content);
      const anchor=document.createElement("a");
      anchor.href=address;
      anchor.download="geoprospect-"+run.id+(kind==="targets"?"-targets.geojson":kind==="provenance"?"-provenance.json":kind==="sensitivity"?"-sensitivity.json":"-score.tif");
      anchor.click();
      setTimeout(()=>URL.revokeObjectURL(address),5000);
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  const field=(label:string,value:string,set:(s:string)=>void,step="0.1")=>
    <label className="field">{label}<input type="number" value={value} onChange={e=>set(e.target.value)} step={step}/></label>;
  return <div className="panel-body targeting-panel">
    <div className="index-notice">
      <strong>Modelo multicritério interpretável</strong>
      <p>Combine indicadores espectrais, distância a falhas e litologias favoráveis.
        A pontuação 0–1 representa favorabilidade relativa, não probabilidade de minério.</p>
    </div>
    {error&&<div className="error" role="alert">{error}</div>}
    {notice&&<div className="notice">{notice}</div>}
    <label className="field">Raster espectral de referência
      <select value={rasterId} onChange={e=>setRasterId(e.target.value)}>
        {rasters.length===0&&<option value="">Nenhum raster concluído</option>}
        {rasters.map(r=><option value={r.id} key={r.id}>{r.index.toUpperCase()} · {r.id.slice(0,8)}</option>)}
      </select>
    </label>
    {rasters.length===0&&<p className="disclaimer">Execute primeiro um índice Sentinel-2 na secção «Índices espectrais».</p>}
    <div className="raster-dates">{field("Normalização mínima",minimum,setMinimum)}{field("Normalização máxima",maximum,setMaximum)}</div>
    <label className="inline-check"><input type="checkbox" checked={invert} onChange={e=>setInvert(e.target.checked)}/> Inverter favorabilidade espectral</label>
    {field("Peso espectral",spectralWeight,setSpectralWeight)}
    <div className="list-label">EVIDÊNCIA ESTRUTURAL (OPCIONAL)</div>
    <label className="field">Falhas / lineamentos
      <select value={faultId} onChange={e=>setFaultId(e.target.value)}>
        <option value="">Não incluir</option>
        {faults.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}
      </select>
    </label>
    {faultId&&<div className="raster-dates">{field("Peso estrutural",faultWeight,setFaultWeight)}{field("Distância (km)",distanceKm,setDistanceKm)}</div>}
    <div className="list-label">EVIDÊNCIA GEOLÓGICA (OPCIONAL)</div>
    <label className="field">Mapa de litologias
      <select value={geologyId} onChange={e=>setGeologyId(e.target.value)}>
        <option value="">Não incluir</option>
        {lithologies.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}
      </select>
    </label>
    {geologyId&&<>
      {field("Peso geológico",geologyWeight,setGeologyWeight)}
      <label className="field">Nome do campo de classe<input type="text" value={lithologyField} onChange={e=>setLithologyField(e.target.value)}/></label>
      <label className="field">Valores favoráveis (separados por vírgula)<input value={favorable} onChange={e=>setFavorable(e.target.value)} placeholder="Ex.: máfica, metavulcânica"/></label>
    </>}
    <div className="list-label">IDENTIFICAÇÃO DE ALVOS</div>
    <div className="raster-dates">{field("Limiar 0–1",threshold,setThreshold,"0.05")}{field("Área mínima (pixels)",minPixels,setMinPixels,"1")}</div>
    <p className="disclaimer">Os pesos são normalizados automaticamente. Áreas sem cobertura das evidências seleccionadas permanecem sem pontuação.</p>
    <button className="primary" disabled={busy||!rasterId} onClick={()=>void submit()}><Play size={15}/> Executar modelo</button>
    <div className="list-label">HISTÓRICO ({runs.length}) <button className="refresh-button" onClick={()=>void refresh()} aria-label="Actualizar"><RefreshCw size={14}/></button></div>
    {runs.length===0&&<div className="empty"><Target size={25}/><p>Sem modelos neste projecto.</p></div>}
    {runs.map(run=><div className="raster-job" key={run.id}>
      <div className="raster-job-title"><b>Prospectividade</b><span className={"raster-status "+run.status}>{run.status}</span></div>
      <small>{new Date(run.created_at).toLocaleString("pt-PT")} · Limiar: {run.config.target_threshold}</small>
      {run.stats&&<div className="targeting-summary">
        <strong>{run.stats.targets} alvos</strong>
        <span>Índice médio {run.stats.mean.toFixed(3)} · Cobertura {(run.stats.valid_fraction*100).toFixed(1)}%</span>
        <small>Evidências: {run.stats.inputs.join(", ")} · Referência {run.stats.metric_crs}</small>
        {run.stats.sensitivity&&<small>Sensibilidade ±20%: {(run.stats.sensitivity.max_threshold_flip_fraction*100).toFixed(2)}% de pixels alteraram a classe no pior cenário</small>}
      </div>}
      {run.error&&<small className="raster-error">{run.error}</small>}
      {run.status==="completed"&&<div className="raster-actions wrap-actions">
        <button disabled={busy} onClick={()=>void view(run)}><Eye size={14}/> Ver mapa</button>
        <button disabled={busy} onClick={()=>void download(run,"targets")}><CloudDownload size={14}/> Alvos</button>
        <button disabled={busy} onClick={()=>void download(run,"geotiff")}><CloudDownload size={14}/> GeoTIFF</button>
        <button disabled={busy} onClick={()=>void download(run,"provenance")}><CloudDownload size={14}/> Metadados</button>
        <button disabled={busy} onClick={()=>void download(run,"sensitivity")}><CloudDownload size={14}/> Sensibilidade</button>
      </div>}
    </div>)}
  </div>;
}
