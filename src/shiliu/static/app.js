const postJson=async(url,body)=>{const response=await fetch(url,{method:'POST',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok||data.ok===false)throw new Error(data.error||`HTTP ${response.status}`);return data};

const pollRun=(runId,status,button)=>{const started=Date.now();const timer=setInterval(async()=>{try{const data=await fetch(`/api/sync-runs/${runId}`).then(r=>r.json()),run=data.run;const elapsed=Math.max(0,Math.round((Date.now()-started)/1000));status.textContent=`${run.message||run.current_phase||'处理中'} · 新增 ${run.discovered_count||0} · 已处理 ${run.processed_count||0} · 历史待处理 ${run.history_pending_count||0} · ${elapsed}s`;if(run.status!=='running'){clearInterval(timer);button&&(button.disabled=false);if(run.status==='completed'||run.status==='completed_with_errors'){status.textContent=`同步完成：新增 ${run.discovered_count||0}，处理 ${run.processed_count||0}，历史待处理 ${run.history_pending_count||0}`;setTimeout(()=>location.reload(),800)}else{status.textContent=run.error_summary||run.message||`任务状态：${run.status}`}}}catch(error){clearInterval(timer);button&&(button.disabled=false);status.textContent=error.message}},1200)};

document.querySelector('[data-sync]')?.addEventListener('click',async event=>{const button=event.currentTarget,status=document.querySelector('[data-sync-status]');button.disabled=true;status.textContent='正在启动同步…';try{const data=await postJson(button.dataset.syncUrl||'/api/sync');status.textContent=data.reused?'已有同步正在运行，已连接进度。':'同步已进入后台。';pollRun(data.run_id,status,button)}catch(error){status.textContent=error.message;button.disabled=false}});

document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',async()=>{const card=button.closest('[data-video-id]'),id=card.dataset.videoId,action=button.dataset.action;button.disabled=true;try{const data=await postJson(`/api/videos/${id}/${action}`);if(data.run_id){const status=document.querySelector('[data-sync-status]');pollRun(data.run_id,status,button)}else{location.reload()}}catch(error){alert(error.message);button.disabled=false}}));

const loginButton=document.querySelector('[data-start-login]');
let loginPollTimer=null;
const showLoginQr=data=>{const box=document.querySelector('[data-qr-box]'),image=document.querySelector('[data-qr]'),status=document.querySelector('[data-login-status]');if(data.qr_url){image.src=`${data.qr_url}?t=${Date.now()}`;box.hidden=false}status.textContent=data.reused?'已恢复正在等待的二维码，请扫码并在手机确认。':'等待扫码并在手机确认…';if(loginPollTimer)clearInterval(loginPollTimer);loginPollTimer=setInterval(async()=>{const state=await fetch('/api/setup/bilibili-login/status').then(r=>r.json());if(state.status==='completed'){clearInterval(loginPollTimer);loginPollTimer=null;status.textContent='登录成功，可以刷新收藏夹。';loginButton.disabled=false}else if(state.status==='failed'){clearInterval(loginPollTimer);loginPollTimer=null;status.textContent='二维码过期或登录失败，请重新生成。';loginButton.disabled=false}},1800)};
loginButton?.addEventListener('click',async()=>{loginButton.disabled=true;try{showLoginQr(await postJson('/api/setup/bilibili-login'))}catch(error){alert(error.message);loginButton.disabled=false}});
if(loginButton){fetch('/api/setup/bilibili-login/status').then(response=>response.json()).then(state=>{if(state.status==='waiting'&&state.qr_url){loginButton.disabled=true;showLoginQr({qr_url:state.qr_url,reused:true})}}).catch(()=>{})}

const folderButton=document.querySelector('[data-load-folders]');
folderButton?.addEventListener('click',async()=>{folderButton.disabled=true;try{const data=await fetch('/api/setup/folders').then(r=>r.json());if(!data.ok)throw new Error(data.error);const select=document.querySelector('[name=favorite_id]'),saved=select.dataset.savedValue;select.innerHTML='';data.folders.forEach(folder=>{const option=document.createElement('option');option.value=folder.id;option.dataset.title=folder.title||'';option.textContent=`${folder.title} · ${folder.media_count||0} 条`;if(String(folder.id)===saved)option.selected=true;select.appendChild(option)})}catch(error){alert(error.message)}finally{folderButton.disabled=false}});

const setupForm=document.querySelector('[data-setup-form]');
const modelButton=document.querySelector('[data-load-models]');
modelButton?.addEventListener('click',async()=>{const fields=new FormData(setupForm);modelButton.disabled=true;try{const model=fields.get('interactive_model')||fields.get('model');const data=await postJson('/api/setup/models',{base_url:fields.get('base_url'),api_key:fields.get('api_key'),model,thinking_enabled:true,reasoning_effort:'high'});const select=document.querySelector('[data-model-list]');select.innerHTML='<option value="">选择模型</option>';data.models.forEach(value=>select.add(new Option(value,value)))}catch(error){alert(error.message)}finally{modelButton.disabled=false}});

document.querySelectorAll('[data-test-role]').forEach(button=>button.addEventListener('click',async()=>{const fields=new FormData(setupForm),status=document.querySelector('[data-model-status]'),role=button.dataset.testRole,isIngestion=role==='ingestion_model';button.disabled=true;status.textContent=`正在测试 ${fields.get(role)}…`;try{const data=await postJson('/api/setup/test-provider',{base_url:fields.get('base_url'),api_key:fields.get('api_key'),model:fields.get(role),thinking_enabled:!isIngestion,reasoning_effort:'high'});status.textContent=`${role} 连接成功：${data.result}`}catch(error){status.textContent=`${role} 连接失败：${error.message}`}finally{button.disabled=false}}));

const setupPayload=fields=>({content_dir:fields.get('content_dir'),favorite_id:fields.get('favorite_id')?Number(fields.get('favorite_id')):null,favorite_title:setupForm.elements.favorite_id?.selectedOptions[0]?.dataset.title||'',base_url:fields.get('base_url'),api_key:fields.get('api_key'),model:fields.get('interactive_model'),ingestion_model:fields.get('ingestion_model'),interactive_model:fields.get('interactive_model'),taxonomy_model:fields.get('taxonomy_model'),fast_transcript_model:fields.get('ingestion_model'),formal_transcript_model:fields.get('ingestion_model'),formal_summary_model:fields.get('ingestion_model'),thinking_enabled:true,reasoning_effort:'high'});
const saveDraftButton=document.querySelector('[data-save-draft]');
saveDraftButton?.addEventListener('click',async()=>{const fields=new FormData(setupForm),status=document.querySelector('[data-model-status]');saveDraftButton.disabled=true;status.textContent='正在保存到本机…';try{await postJson('/api/setup/draft',setupPayload(fields));setupForm.elements.api_key.value='';status.textContent='设置草稿已保存；API Key 已进入 macOS Keychain。'}catch(error){status.textContent=`保存失败：${error.message}`}finally{saveDraftButton.disabled=false}});

setupForm?.addEventListener('submit',async event=>{event.preventDefault();const fields=new FormData(setupForm),status=document.querySelector('[data-setup-status]'),button=setupForm.querySelector('[type=submit]'),payload=setupPayload(fields);payload.confirm_baseline=fields.get('confirm_baseline')==='on';payload.install_scheduler=fields.get('install_scheduler')==='on';button.disabled=true;status.textContent='正在测试模型、读取当前收藏夹并建立基线…';try{const data=await postJson('/api/setup/complete',payload);status.textContent=`设置完成：${data.baseline_count} 条历史内容已建立基线。`;setTimeout(()=>location.href='/',900)}catch(error){status.textContent=error.message;button.disabled=false}});

const sourceUrl=document.querySelector('[data-source-url]'),previewButton=document.querySelector('[data-preview-source]'),addSourceButton=document.querySelector('[data-add-source]'),sourcePreview=document.querySelector('[data-source-preview]'),sourceStatus=document.querySelector('[data-source-status]'),historyPolicy=document.querySelector('[data-history-policy]'),historyCustom=document.querySelector('[data-history-custom]');
let previewedSource=null;
historyPolicy?.addEventListener('change',()=>{historyCustom.hidden=historyPolicy.value!=='latest_n:custom'});
previewButton?.addEventListener('click',async()=>{previewButton.disabled=true;sourceStatus.textContent='正在只读预览…';try{const data=await postJson('/api/sources/preview',{url:sourceUrl.value});previewedSource=data.preview;sourcePreview.hidden=false;sourcePreview.textContent=`${data.preview.account_name} · ${data.preview.folder_title} · ${data.preview.media_count} 条${data.already_added?' · 已添加':''}`;addSourceButton.disabled=data.already_added;sourceStatus.textContent='预览不会导入或处理视频。'}catch(error){sourceStatus.textContent=error.message;addSourceButton.disabled=true}finally{previewButton.disabled=false}});
addSourceButton?.addEventListener('click',async()=>{if(!previewedSource)return;addSourceButton.disabled=true;const selected=historyPolicy.value;let history_policy='future_only',history_limit=null;if(selected==='all'){history_policy='all'}else if(selected.startsWith('latest_n')){history_policy='latest_n';const value=selected.split(':')[1];history_limit=value==='custom'?Number(document.querySelector('[data-history-limit]').value):Number(value)}sourceStatus.textContent='正在读取收藏夹并建立来源…';try{const data=await postJson('/api/sources',{url:sourceUrl.value,history_policy,history_limit});sourceStatus.textContent=`来源已添加：基线 ${data.baseline_count} 条，历史待处理 ${data.history_queued} 条。`;setTimeout(()=>location.reload(),800)}catch(error){sourceStatus.textContent=error.message;addSourceButton.disabled=false}});

document.querySelectorAll('[data-source-action]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{await postJson(`/api/sources/${button.dataset.sourceId}/${button.dataset.sourceAction}`);location.reload()}catch(error){alert(error.message);button.disabled=false}}));
document.querySelectorAll('[data-source-move]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{await postJson(`/api/sources/${button.dataset.sourceId}/move`,{direction:button.dataset.sourceMove});location.reload()}catch(error){alert(error.message);button.disabled=false}}));
document.querySelectorAll('[data-source-sync]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{const data=await postJson(`/api/sources/${button.dataset.sourceSync}/sync`);sourceStatus.textContent='同步已进入后台。';pollRun(data.run_id,sourceStatus,button)}catch(error){sourceStatus.textContent=error.message;button.disabled=false}}));

const saveAsrButton=document.querySelector('[data-save-asr]');
saveAsrButton?.addEventListener('click',async()=>{const status=document.querySelector('[data-asr-status]');saveAsrButton.disabled=true;status.textContent='正在测试 Paraformer 连接…';try{const data=await postJson('/api/setup/asr',{base_url:document.querySelector('[data-asr-base-url]').value,api_key:document.querySelector('[data-asr-api-key]').value,model:document.querySelector('[data-asr-model]').value});document.querySelector('[data-asr-api-key]').value='';status.textContent=data.result}catch(error){status.textContent=`连接失败：${error.message}`}finally{saveAsrButton.disabled=false}});

const masonry=document.querySelector('.waterfall');
if(masonry){const cards=[...masonry.querySelectorAll('.video-card')],gap=()=>Number.parseFloat(getComputedStyle(masonry).getPropertyValue('--masonry-gap'))||24;let frame=0;const layout=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const spacing=gap();cards.forEach(card=>{const span=Math.max(1,Math.ceil(card.getBoundingClientRect().height+spacing));const value=`span ${span}`;if(card.style.gridRowEnd!==value)card.style.gridRowEnd=value})})};if('ResizeObserver'in window){const observer=new ResizeObserver(layout);cards.forEach(card=>observer.observe(card))}window.addEventListener('resize',layout,{passive:true});masonry.querySelectorAll('details').forEach(item=>item.addEventListener('toggle',layout));masonry.querySelectorAll('img').forEach(image=>{if(!image.complete)image.addEventListener('load',layout,{once:true})});document.fonts?.ready.then(layout);layout()}

const classifyLibraryCover=image=>{
  const frame=image.closest('.cover-wrap');
  if(!frame||!image.naturalWidth||!image.naturalHeight)return;
  frame.classList.toggle('is-portrait-cover',image.naturalHeight>image.naturalWidth*1.08);
  try{
    const width=48,height=27,canvas=document.createElement('canvas');
    canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d',{willReadFrequently:true});
    context.drawImage(image,0,0,width,height);
    const pixels=context.getImageData(0,0,width,height).data,columns=[];
    for(let x=0;x<width;x++){
      let total=0;
      for(let y=0;y<height;y++){
        const offset=(y*width+x)*4;
        total+=(pixels[offset]*.2126)+(pixels[offset+1]*.7152)+(pixels[offset+2]*.0722);
      }
      columns.push(total/height);
    }
    const center=columns.slice(18,30).reduce((sum,value)=>sum+value,0)/12;
    const threshold=Math.min(42,center*.42);
    let left=0,right=width-1;
    while(left<width/2&&columns[left]<threshold)left++;
    while(right>width/2&&columns[right]<threshold)right--;
    const contentWidth=right-left+1;
    if(center>58&&left>=4&&right<=width-5&&contentWidth>=12){
      const zoom=Math.min(2.2,width/contentWidth);
      frame.style.setProperty('--cover-zoom',zoom.toFixed(3));
      frame.classList.add('is-pillarboxed');
    }
  }catch(_error){
    frame.style.removeProperty('--cover-zoom');
    frame.classList.remove('is-pillarboxed');
  }
};
document.querySelectorAll('.cover-wrap img').forEach(image=>{
  if(image.complete)classifyLibraryCover(image);
  else image.addEventListener('load',()=>classifyLibraryCover(image),{once:true});
});
