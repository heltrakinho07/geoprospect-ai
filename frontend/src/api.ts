export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function api<T>(path:string, options:RequestInit={}, token?:string):Promise<T>{
  const response=await fetch(API_URL+path,{
    ...options,
    headers:{"Content-Type":"application/json",...(token?{"Authorization":"Bearer "+token}:{}),...(options.headers||{})}
  });
  if(!response.ok){
    let detail:string;
    try {
      const data=await response.json();
      detail=typeof data.detail==="string"?data.detail:JSON.stringify(data.detail||data);
    }catch{detail="Erro HTTP "+response.status;}
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
