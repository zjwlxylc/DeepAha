// Optional same-origin front door for deployments retaining a separate web port.
// The application itself is served by FastAPI; this proxy never starts legacy Next.
import http from 'node:http';
import https from 'node:https';
const target=new URL(process.env.DEEPAHA_API_ORIGIN||'http://127.0.0.1:8000');
if(!['http:','https:'].includes(target.protocol)||target.username||target.password)throw new Error('Invalid API origin');
const transport=target.protocol==='https:'?https:http;
const server=http.createServer((req,res)=>{
 const upstream=transport.request({hostname:target.hostname,port:target.port,protocol:target.protocol,path:req.url,method:req.method,headers:{...req.headers}},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
 upstream.setTimeout(req.url.split('?')[0]==='/api/manage/scout/previews'?180000:30000,()=>upstream.destroy());
 upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'Content-Type':'text/plain; charset=utf-8'});res.end('服务暂不可用');});
 req.on('aborted',()=>upstream.destroy());req.pipe(upstream);
});
server.listen(Number(process.env.PORT||3000),process.env.HOST||'127.0.0.1',()=>console.log('DeepAha web front door ready'));
