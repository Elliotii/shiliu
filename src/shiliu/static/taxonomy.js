const taxonomySources=document.querySelector('[data-taxonomy-sources]');
if(taxonomySources){
  const previewButton=document.querySelector('[data-taxonomy-preview]'),freezeButton=document.querySelector('[data-taxonomy-freeze]'),status=document.querySelector('[data-taxonomy-status]'),panel=document.querySelector('[data-taxonomy-preview-panel]'),metrics=document.querySelector('[data-taxonomy-metrics]'),samples=document.querySelector('[data-taxonomy-samples]');
  let previewedSelection=[];
  const selected=()=>[...taxonomySources.querySelectorAll('input:checked')].map(input=>Number(input.value));
  const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const request=async(url,source_ids)=>{const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_ids})});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'请求失败');return data};
  const render=preview=>{
    const values=[['收藏关系',preview.membership_count],['去重 Card',preview.total_cards],['Discovery Eligible',preview.discovery_eligible_count],['Trial-only',preview.trial_assignment_only_count],['重复关系合并',preview.duplicate_memberships_merged],['A / B / C / D',`${preview.evidence_counts.A} / ${preview.evidence_counts.B} / ${preview.evidence_counts.C} / ${preview.evidence_counts.D}`]];
    metrics.innerHTML=values.map(([label,value])=>`<div><small>${label}</small><strong>${value}</strong></div>`).join('');
    samples.innerHTML=preview.sample_cards.map(card=>`<details><summary><span class="evidence evidence-${card.evidence_level.toLowerCase()}">${card.evidence_level}</span>${escapeHtml(card.stored_card.title)}</summary><div class="card-compare"><section><h3>Stored Card</h3><pre>${escapeHtml(JSON.stringify(card.stored_card,null,2))}</pre></section><section><h3>Discovery View</h3><pre>${escapeHtml(JSON.stringify(card.discovery_view,null,2))}</pre></section></div></details>`).join('');
    panel.hidden=false;
  };
  taxonomySources.addEventListener('change',()=>{freezeButton.disabled=true;previewedSelection=[];status.textContent='选择已变化，请重新预览。'});
  previewButton?.addEventListener('click',async()=>{const source_ids=selected();if(!source_ids.length){status.textContent='请先选择至少一个收藏夹。';return}previewButton.disabled=true;status.textContent='正在本地生成预览，不会调用模型…';try{const data=await request('/api/taxonomy/snapshots/preview',source_ids);render(data.preview);previewedSelection=source_ids;freezeButton.disabled=data.preview.total_cards===0;status.textContent='预览完成。'}catch(error){status.textContent=error.message}finally{previewButton.disabled=false}});
  freezeButton?.addEventListener('click',async()=>{if(!previewedSelection.length)return;freezeButton.disabled=true;status.textContent='正在冻结 Snapshot…';try{const data=await request('/api/taxonomy/snapshots',previewedSelection);status.textContent=`Snapshot #${data.snapshot.snapshot_id} 已${data.snapshot.reused?'复用':'冻结'}，Hash ${data.snapshot.snapshot_hash.slice(0,12)}…`;setTimeout(()=>location.reload(),900)}catch(error){status.textContent=error.message;freezeButton.disabled=false}});
}
