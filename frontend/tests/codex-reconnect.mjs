import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
let cursor=0, dirty=false, tree, timer, saved, saveFails=true;
const cells=[], effects=[], session=new Map();
const react={
 useState(initial){const i=cursor++;if(!(i in cells))cells[i]=typeof initial==='function'?initial():initial;return [cells[i],next=>{const v=typeof next==='function'?next(cells[i]):next;if(!Object.is(v,cells[i])){cells[i]=v;dirty=true;}}];},
 useRef(initial){return react.useState(()=>({current:initial}))[0];},
 useId(){return 'model-list';},
 useEffect(fn,deps){const i=cursor++,old=cells[i];if(!old||deps.some((v,n)=>!Object.is(v,old.deps[n]))){cells[i]={deps};effects.push(()=>{old?.cleanup?.();cells[i].cleanup=fn();});}},
};
const jsx=(type,props)=>({type,props:props||{}});
function compile(file,modules,extra={}){
 const ctx={exports:{},require:name=>modules[name]||{},...extra};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,ctx);
 return ctx.exports;
}
const choices=compile('../src/lib/ai-access.ts',{});
let job={status:'idle'}, logged=false;
const api={
 loadAgentConnection:()=>null,
 saveAgentConnection:async c=>{if(saveFails)throw Error('offline');saved=c;},
 AgentRequestError:Error,
 agentRequest:async(path,body)=>{
  if(path==='/status')return {subscription_ready:logged,models:logged?[{model:'model-a'},{model:'model-b'}]:[],default_model:logged?'model-a':''};
  if(path==='/access')return job;
  if(path==='/access/login')return job={id:'login',kind:'login',status:'running',auth_url:'https://auth.openai.com/'};
  if(path==='/access/probe')return job={id:body.request_id,kind:'probe',status:'running'};
  throw Error(path);
 }
};
const component=compile('../src/components/AgentAccess.tsx',{
 react,'react/jsx-runtime':{jsx,jsxs:jsx},'@/lib/ai-access':choices,'@/lib/agent-api':api,
 '@/lib/random-id':{randomId:()=> 'a'.repeat(32)},'@/lib/account':{accountKey:k=>k+':account:alice'},
},{AbortController,setTimeout:fn=>{timer=fn;return 1;},clearTimeout(){},sessionStorage:{getItem:k=>session.get(k)||null,setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)}});
const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
const text=n=>!n||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
async function render(){for(let n=0;n<30;n++){dirty=false;cursor=0;tree=component.AgentAccess({});effects.splice(0).forEach(f=>f());await new Promise(r=>setImmediate(r));if(!dirty)return;}throw Error('render loop');}
const button=label=>nodes(tree).find(n=>n.type==='button'&&text(n)===label);
await render();assert.equal(button('测试连接并保存').props.disabled,true);
await button('登录 ChatGPT').props.onClick();await render();
logged=true;job={id:'login',kind:'login',status:'complete'};await timer();await render();
const model=nodes(tree).find(n=>n.props['aria-label']==='Agent 接入模型');
assert.equal(model.type,'select','Authorized Codex models must be a full dropdown, not a filtered datalist');
assert.deepEqual(nodes(model).filter(n=>n.type==='option').map(n=>n.props.value),['model-a','model-b','']);
assert.equal(model.props.value,'model-a');model.props.onChange({target:{value:'model-b'}});await render();
await button('测试连接并保存').props.onClick();await render();
assert.ok([...session.keys()].every(k=>k.endsWith(':account:alice')));
job={...job,status:'complete'};await timer();await render();
assert.equal(saved,undefined);assert.equal(session.size,1,'Failed persistence keeps the recoverable tested configuration');
saveFails=false;await timer();await render();
assert.equal(saved.provider,'codex-private');assert.equal(saved.model,'model-b');assert.equal(session.size,0);
nodes(tree).find(n=>n.props['aria-label']==='Agent 接入模型').props.onChange({target:{value:''}});await render();
assert.ok(nodes(tree).find(n=>n.props['aria-label']==='其他模型标识'),'Custom model entry remains available');
console.log('Unified Codex login → model selection → probe → recoverable account save passed.');
