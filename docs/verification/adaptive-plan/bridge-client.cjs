const {spawn}=require('child_process');
const readline=require('readline');
module.exports=function startBridge(command,cwd){
  if(!command)throw Error('Set ADAPTIVE_PLAN_BRIDGE_COMMAND');
  const bridge=spawn(command,{cwd,shell:true,stdio:['pipe','pipe','inherit']});
  const pending=[];let queue=Promise.resolve();
  readline.createInterface({input:bridge.stdout}).on('line',line=>{
    if(!line.startsWith('PLAN_RESULT '))return;
    try{pending.shift()?.resolve(JSON.parse(line.slice(12)))}catch(error){pending.shift()?.reject(error)}
  });
  bridge.on('exit',code=>{while(pending.length)pending.shift().reject(Error(`Bridge exited ${code}`))});
  function api(method,path,body,user='1'){
    const run=()=>new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error(`Bridge timed out: ${method} ${path}`)),15000);
      pending.push({resolve:value=>{clearTimeout(timer);resolve(value)},reject:error=>{clearTimeout(timer);reject(error)}});
      bridge.stdin.write(JSON.stringify({method,path,body,user})+'\n');
    });
    const result=queue.then(run);queue=result.catch(()=>{});return result;
  }
  return {api,close:()=>{bridge.stdin.end();bridge.kill()}};
};
