import {useCallback,useEffect,useState} from "react";
import {api,API_URL} from "./api";
import {CloudDownload,Eye,Layers,Play,RefreshCw} from "lucide-react";

type Job={
  id:string;index:string;status:string;date_from:string;date_to:string;
  max_cloud:number;error?:string;created_at:string;
  stats?:{min:number;max:number;mean:number;valid_fraction:number;bounds:number[];width:number;height:number};
};
type Settings={configured:boolean;indices:{id:string;description:string}[];limits:{daily_jobs:number};notice:string};
export type RasterOverlay={url:string;bounds:number[]};

export default function RasterPanel({orgId,projectId,token,onPreview}:{
  orgId:string;projectId:string;token:string;onPreview:(v:RasterOverlay)=>void;
}){
  const [config,setConfig]=useState<Settings|null>(null);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [index,setIndex]=useState("ndvi");
  const [start,setStart]=useState("2025-01-01"),[end,setEnd]=useState("2025-01-20");
  const [cloud,setCloud]=useState(25),[working,setWorking]=useState(false),[error,setError]=useState(""),[info,setInfo]=useState("");
  const prefix="/v1/orgs/"+encodeURIComponent(orgId)+"/projects/"+encodeURIComponent(projectId)+"/raster";
  const refresh=useCallback(async()=>{
    const list=await api<Job[]>(prefix+"/jobs",{},token);
    setJobs(list);
  },[prefix,token]);
  useEffect(()=>{
    let closed=false;
    setJobs([]);setError("");setInfo("");
    api<Settings>(prefix+"/config",{},token).then(v=>{if(!closed)setConfig(v);}).catch(e=>{if(!closed)setError(String(e));});
    refresh().catch(e=>{if(!closed)setError(String(e));});
    const timer=setInterval(()=>refresh().catch(()=>{}),5000);
    return ()=>{closed=true;clearInterval(timer);};
  },[prefix,token,refresh]);
  async function create(){
    setWorking(true);setInfo("");setError("");
    try{
      await api<Job>(prefix+"/jobs",{method:"POST",body:JSON.stringify({index,date_from:start,date_to:end,max_cloud:cloud})},token);
      setInfo("Processamento registado. Os resultados aparecerão nesta lista.");await refresh();
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setWorking(false);}
  }
  async function getAsset(job:Job,kind:"preview"|"geotiff"){
    setWorking(true);setError("");
    try{
      const response=await fetch(API_URL+prefix+"/jobs/"+job.id+"/"+kind,{headers:{"Authorization":"Bearer "+token}});
      if(!response.ok)throw new Error("Não foi possível obter o ficheiro ("+response.status+").");
      const blob=await response.blob();const url=URL.createObjectURL(blob);
      if(kind==="preview"){
        if(!job.stats?.bounds){URL.revokeObjectURL(url);throw new Error("O resultado não tem extensão espacial.");}
        onPreview({url,bounds:job.stats.bounds});
      }else{
        const anchor=document.createElement("a");anchor.href=url;anchor.download=job.index+"-"+job.id+".tif";anchor.click();
        setTimeout(()=>URL.revokeObjectURL(url),3000);
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setWorking(false);}
  }
  return <div className="panel-body raster-panel">
    <div className="index-notice">Imagens Sentinel-2 L2A · Índices indicativos, não detecção directa de minério.</div>
    {config&&!config.configured&&<div className="error">Para executar análises é necessário configurar as credenciais OAuth Sentinel Hub no servidor.</div>}
    {error&&<div className="error" role="alert">{error}</div>}
    {info&&<div className="notice">{info}</div>}
    <label className="field">Índice espectral
      <select value={index} onChange={e=>setIndex(e.target.value)}>
        {(config?.indices||[{id:"ndvi",description:"NDVI"}]).map(i=><option key={i.id} value={i.id}>{i.id.toUpperCase()} — {i.description}</option>)}
      </select>
    </label>
    <div className="raster-dates">
      <label className="field">Desde<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label className="field">Até<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
    </div>
    <label className="field">Cobertura de nuvens até {cloud}%<input type="range" min="0" max="100" step="5" value={cloud} onChange={e=>setCloud(Number(e.target.value))}/></label>
    <button className="primary" onClick={()=>void create()} disabled={working||!config?.configured}><Play size={15}/> Iniciar processamento</button>
    <div className="list-label">RESULTADOS ({jobs.length}) <button className="refresh-button" onClick={()=>void refresh()} aria-label="Actualizar processamentos"><RefreshCw size={14}/></button></div>
    {jobs.length===0&&<div className="empty"><Layers size={22}/><p>Sem análises neste projecto.</p></div>}
    {jobs.map(j=><div className="raster-job" key={j.id}>
      <div className="raster-job-title"><b>{j.index.toUpperCase()}</b><span className={"raster-status "+j.status}>{j.status}</span></div>
      <small>{j.date_from} → {j.date_to}</small>
      {j.stats&&<small>Pixels válidos: {(j.stats.valid_fraction*100).toFixed(1)}% · Média: {j.stats.mean.toFixed(3)}</small>}
      {j.error&&<small className="raster-error">{j.error}</small>}
      {j.status==="completed"&&<div className="raster-actions">
        <button onClick={()=>void getAsset(j,"preview")} disabled={working}><Eye size={14}/> Ver mapa</button>
        <button onClick={()=>void getAsset(j,"geotiff")} disabled={working}><CloudDownload size={14}/> GeoTIFF</button>
      </div>}
    </div>)}
    <p className="disclaimer">R2 piloto: processamento limitado a 384 × 384 pixels e intervalo de 31 dias. Trabalhos são executados no backend da instância; esta não é uma fila distribuída de produção.</p>
  </div>;
}
