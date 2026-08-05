(function(global){
  'use strict';

  const capabilityMap={
    auth:['signIn','signOut','isSignedIn','getUser','getMonthlyUsage','getDetailedAppUsage'],
    ai:['chat','listModels','listModelProviders','txt2img','img2txt','txt2speech','txt2vid','speech2txt','speech2speech'],
    fs:['write','read','mkdir','readdir','rename','copy','move','stat','delete','getReadURL','upload'],
    kv:['set','get','list','incr','decr','del','flush'],
    apps:['create','list','delete','update','get','checkName'],
    hosting:['create','list','delete','update','get'],
    workers:['create','delete','list','get','exec']
  };

  function api(){
    if(!global.puter)throw new Error('Puter.js did not load. Check network access and the Puter CDN script.');
    return global.puter;
  }

  function has(path){
    return path.split('.').reduce((value,key)=>value&&value[key],api())!==undefined;
  }

  function inspect(){
    const result={loaded:Boolean(global.puter),groups:{}};
    if(!global.puter)return result;
    for(const [group,methods] of Object.entries(capabilityMap)){
      result.groups[group]={available:Boolean(global.puter[group]),methods:{}};
      for(const method of methods)result.groups[group].methods[method]=has(group+'.'+method);
    }
    result.groups.ai.methods.listTTSEngines=has('ai.txt2speech.listEngines');
    result.groups.ai.methods.listTTSVoices=has('ai.txt2speech.listVoices');
    return result;
  }

  async function ensureSignedIn(options={}){
    const puter=api();
    if(puter.auth?.isSignedIn?.())return puter.auth.getUser?.();
    if(options.interactive===false)throw new Error('Puter account authorization is required.');
    return puter.auth.signIn(options.signInOptions||{});
  }

  function requireCapability(path){
    if(!has(path))throw new Error('This Puter capability is unavailable in the loaded SDK: '+path);
  }

  async function call(path,args=[],options={}){
    requireCapability(path);
    if(options.auth)await ensureSignedIn(options);
    const parts=path.split('.');
    const method=parts.pop();
    const owner=parts.reduce((value,key)=>value[key],api());
    return owner[method](...args);
  }

  const platform={
    inspect,
    has,
    ensureSignedIn,
    auth:{
      signIn:options=>call('auth.signIn',[options||{}]),
      signOut:()=>call('auth.signOut'),
      isSignedIn:()=>Boolean(api().auth?.isSignedIn?.()),
      user:()=>call('auth.getUser',[],{auth:true}),
      monthlyUsage:()=>call('auth.getMonthlyUsage',[],{auth:true}),
      detailedUsage:(...args)=>call('auth.getDetailedAppUsage',args,{auth:true})
    },
    ai:{
      chat:(messages,options={})=>call('ai.chat',[messages,options]),
      models:provider=>call('ai.listModels',provider?[provider]:[]),
      providers:()=>call('ai.listModelProviders'),
      image:(prompt,options={})=>call('ai.txt2img',[prompt,options]),
      describeImage:(image,options={})=>call('ai.img2txt',[image,options]),
      speech:(text,options={})=>call('ai.txt2speech',[text,options]),
      video:(prompt,options={})=>call('ai.txt2vid',[prompt,options]),
      transcribe:(audio,options={})=>call('ai.speech2txt',[audio,options]),
      changeVoice:(audio,options={})=>call('ai.speech2speech',[audio,options]),
      ttsEngines:()=>call('ai.txt2speech.listEngines'),
      ttsVoices:(...args)=>call('ai.txt2speech.listVoices',args)
    },
    fs:{
      write:(path,data,options={})=>call('fs.write',[path,data,options],{auth:true}),
      read:(path,options={})=>call('fs.read',[path,options],{auth:true}),
      mkdir:(path,options={})=>call('fs.mkdir',[path,options],{auth:true}),
      list:(path='.',options={})=>call('fs.readdir',[path,options],{auth:true}),
      rename:(source,name)=>call('fs.rename',[source,name],{auth:true}),
      copy:(source,destination,options={})=>call('fs.copy',[source,destination,options],{auth:true}),
      move:(source,destination,options={})=>call('fs.move',[source,destination,options],{auth:true}),
      stat:path=>call('fs.stat',[path],{auth:true}),
      remove:(path,options={})=>call('fs.delete',[path,options],{auth:true}),
      readURL:(path,options={})=>call('fs.getReadURL',[path,options],{auth:true}),
      upload:(files,path,options={})=>call('fs.upload',[files,path,options],{auth:true})
    },
    kv:{
      set:(key,value)=>call('kv.set',[key,value],{auth:true}),
      get:key=>call('kv.get',[key],{auth:true}),
      list:(pattern='*',returnValues=true)=>call('kv.list',[pattern,returnValues],{auth:true}),
      increment:(key,amount=1)=>call('kv.incr',[key,amount],{auth:true}),
      decrement:(key,amount=1)=>call('kv.decr',[key,amount],{auth:true}),
      remove:key=>call('kv.del',[key],{auth:true}),
      flush:()=>call('kv.flush',[],{auth:true})
    },
    apps:{
      create:(name,indexURL,title,description)=>call('apps.create',[name,indexURL,title,description],{auth:true}),
      list:()=>call('apps.list',[],{auth:true}),
      get:name=>call('apps.get',[name],{auth:true}),
      update:(name,options)=>call('apps.update',[name,options],{auth:true}),
      remove:name=>call('apps.delete',[name],{auth:true}),
      checkName:name=>call('apps.checkName',[name],{auth:true})
    },
    hosting:{
      create:(subdomain,dir)=>call('hosting.create',[subdomain,dir],{auth:true}),
      list:()=>call('hosting.list',[],{auth:true}),
      get:subdomain=>call('hosting.get',[subdomain],{auth:true}),
      update:(subdomain,dir)=>call('hosting.update',[subdomain,dir],{auth:true}),
      remove:subdomain=>call('hosting.delete',[subdomain],{auth:true})
    },
    workers:{
      create:(name,filePath,options)=>call('workers.create',[name,filePath,options].filter(value=>value!==undefined),{auth:true}),
      list:()=>call('workers.list',[],{auth:true}),
      get:name=>call('workers.get',[name],{auth:true}),
      execute:(name,options={})=>call('workers.exec',[name,options],{auth:true}),
      remove:name=>call('workers.delete',[name],{auth:true})
    }
  };

  global.NeoGenPuter=Object.freeze(platform);
})(window);
