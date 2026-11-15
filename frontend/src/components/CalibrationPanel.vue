<script setup lang="ts">import {computed,ref,watch} from 'vue';import {fixed,scientific} from '../utils/format';import {canWrite} from '../stores/auth';import {createCalibration} from '../api/calibrations';import {useTask} from '../hooks/useTask';import WarningNotes from './WarningNotes.vue';
const props=defineProps<{runId:string;history:any[];calibration:any|null}>();const emit=defineEmits<{changed:[]}>();
const zones=ref(''),means=ref(''),note=ref('分区实测均值与逐点预测对账；校正只改点值，不改模型和方差。');
const applied=computed(()=>[...props.history].reverse().find(r=>r.state==='applied')||null);
const failed=computed(()=>props.history.filter(r=>r.state==='failed'));
const shown=computed(()=>props.calibration?.payload||applied.value?.payload||null);
const {error,busy,act}=useTask();
watch(()=>props.runId,()=>{zones.value='';means.value='';error.value=''});
async function submit(){await act(async()=>{await createCalibration(props.runId,{zones_csv:zones.value,means_csv:means.value,note:note.value});zones.value='';means.value='';emit('changed')})}
const failure=computed(()=>{if(!error.value)return null;try{const d=JSON.parse(error.value);return d&&typeof d==='object'?d:{message:error.value}}catch{return {message:error.value}}})
const rows=computed(()=>shown.value?.points||[]);
const historyOpen=ref('');
const historyRow=computed(()=>props.history.find(r=>r.id===historyOpen.value)||null);
function download(){const data=JSON.stringify(shown.value,null,2);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([data],{type:'application/json'}));a.download='calibration-'+props.runId+'-'+(shown.value?.version||'none')+'.json';a.click();URL.revokeObjectURL(a.href)}
</script>
<template>
<section class="calibration">
  <div class="section-heading"><h2>分区均值校正</h2><small v-if="shown">当前采用 v{{shown.version}} · 失败版本与旧版本均可回看</small><small v-else>尚未校正，显示原克里金推断</small></div>
  <p class="method-note">导入分区、待估点面积权重与实测均值。校正后各区面积加权均值与外业实测一致；目标是最小化Σ(改变量²/原空间方差)。含水率限制0–100%，零方差点锁定原值。冗余约束自动接受，矛盾约束指出冲突分区。</p>
  <div class="cal-summary" v-if="shown">
    <div><small>目标函数 ΣΔ²/v</small><strong>{{fixed(shown.objective,4)}}</strong></div>
    <div><small>最大分区残差</small><strong>{{scientific(shown.max_zone_residual)}}</strong></div>
    <div><small>最大单点改变量</small><strong>{{fixed(shown.max_point_change)}} pp</strong></div>
    <div><small>约束秩 / 自由点 / 锁定点</small><strong>{{shown.constraints.constraint_rank}} / {{shown.constraints.free_points}} / {{shown.constraints.locked_points}}</strong></div>
  </div>
  <WarningNotes v-if="shown?.warnings?.length" :rows="shown.warnings"/>
  <div v-if="shown" class="table-wrap"><table>
    <thead><tr><th>分区</th><th>实测均值%</th><th>校正前加权均值</th><th>校正后加权均值</th><th>校正前差额</th><th>校正后差额</th><th>权重和</th><th>点数/锁定</th></tr></thead>
    <tbody><tr v-for="z in shown.zones" :key="z.zone_id"><td>{{z.zone_id}}</td><td>{{fixed(z.measured_mean,4)}}</td><td>{{fixed(z.before_mean,4)}}</td><td>{{fixed(z.after_mean,4)}}</td><td>{{fixed(z.delta_before,4)}}</td><td>{{fixed(z.delta_after,6)}}</td><td>{{fixed(z.area_weight_sum,3)}}</td><td>{{z.point_count}} / {{z.locked_point_count}}</td></tr></tbody>
  </table></div>
  <div v-if="shown" class="table-wrap"><table>
    <thead><tr><th>待估点</th><th>原推断%</th><th>校正后%</th><th>改变量 pp</th><th>空间方差 pp²</th><th>状态</th><th>所属分区</th></tr></thead>
    <tbody><tr v-for="p in rows" :key="p.query_id"><td>{{p.query_id}}</td><td>{{fixed(p.before,4)}}</td><td>{{fixed(p.after,4)}}</td><td>{{fixed(p.change,4)}}</td><td>{{fixed(p.variance,4)}}</td><td>{{p.locked?(p.out_of_range_preserved?'零方差锁定（原值越界保留）':'零方差锁定'):'自由校正'}}</td><td>{{p.zones.join(' / ')||'—'}}</td></tr></tbody>
  </table></div>
  <div v-if="failed.length" class="failed-list">
    <h3>失败版本（旧通过版本保持不变）</h3>
    <article v-for="f in failed" :key="f.id" class="failed-row">
      <small>v{{f.version}} · {{f.created_at}} · {{f.actor}}</small>
      <p>{{f.error}}</p>
      <p v-if="f.conflict_zones.length">冲突分区：<b>{{f.conflict_zones.join('、')}}</b></p>
      <div v-if="f.payload?.zones?.length" class="table-wrap"><table>
        <thead><tr><th>冲突分区</th><th>实测均值%</th><th>可达到区间</th><th>单区可满足</th><th>锁定面积占比</th></tr></thead>
        <tbody><tr v-for="z in f.payload.zones" :key="z.zone_id"><td>{{z.zone_id}}</td><td>{{fixed(z.measured_mean,4)}}</td><td>{{fixed(z.achievable_min,4)}}—{{fixed(z.achievable_max,4)}}</td><td>{{z.individually_satisfiable?'是':'否'}}</td><td>{{fixed((z.locked_area_weight_fraction||0)*100,1)}}%</td></tr></tbody>
      </table></div>
    </article>
  </div>
  <form v-if="canWrite()" class="calibration-form" @submit.prevent="submit">
    <h3>导入并联合校正</h3>
    <label>分区权重CSV<textarea v-model="zones" rows="7" required placeholder="zone_id,query_id,area_weight,measured_mean"></textarea></label>
    <small>分区可重叠；同一分区内各待估点面积权重按行给出，均值可选列 measured_mean。</small>
    <label>实测均值CSV（可选，覆盖或补充分区CSV）<textarea v-model="means" rows="4" placeholder="zone_id,measured_mean"></textarea></label>
    <label>提交说明<input v-model="note"></label>
    <div v-if="failure" class="notice" role="alert">{{failure.message||JSON.stringify(failure)}}<span v-if="failure.reason==='conflict'">冲突分区：{{(failure.conflict_zones||[]).join('、')||'未指明'}}。{{failure.kept_version?('旧通过版本 v'+failure.kept_version+' 保持不变。'):'尚无通过版本，保留原克里金推断。'}}</span><span v-else-if="failure.reason==='validation'">{{failure.kept_version?('校验失败，旧通过版本 v'+failure.kept_version+' 保持不变。'):'校验失败，保留原克里金推断。'}}</span><span v-else>输入未通过校验，未生成校正版本。</span></div>
    <div class="actions"><button :disabled="busy">校验并原子替换校正版本</button><button type="button" class="secondary" v-if="shown" @click="download">导出校正版本JSON ↓</button></div>
    <p class="method-note">任一校验失败不替换旧版本：失败原因与冲突分区保留在运行底稿。</p>
  </form>
</section>
<details v-if="props.history.length" class="version-history">
  <summary>校正版本历史（{{props.history.length}}）</summary>
  <div class="table-wrap"><table><thead><tr><th>版本</th><th>状态</th><th>提交人</th><th>时间</th><th>说明</th></tr></thead><tbody>
    <tr v-for="r in props.history" :key="r.id"><td>v{{r.version}}</td><td>{{r.state==='applied'?'已通过（当前）':r.state==='superseded'?'已通过（被替换）':'失败'}}</td><td>{{r.actor}}</td><td>{{r.created_at}}</td><td>{{r.state==='failed'?r.error:('目标值'+fixed(r.payload.objective,3))}}</td><td><button type="button" class="table-action" @click="historyOpen=historyOpen===r.id?'':r.id">{{historyOpen===r.id?'收起':'回看'}}</button></td></tr>
  </tbody></table></div>
  <div v-if="historyRow" class="history-detail">
    <h3>v{{historyRow.version}} · {{historyRow.state==='failed'?'失败原因与可达到区间':'逐点前后值与各区差额'}}</h3>
    <p v-if="historyRow.state==='failed'">{{historyRow.error}}<span v-if="historyRow.conflict_zones.length">（冲突分区：{{historyRow.conflict_zones.join('、')}}）</span></p>
    <div v-if="historyRow.payload?.zones?.length" class="table-wrap"><table><thead><tr><th>分区</th><th>实测均值%</th><th>校正前</th><th>校正后</th><th>可达到区间</th></tr></thead><tbody>
      <tr v-for="z in historyRow.payload.zones" :key="z.zone_id"><td>{{z.zone_id}}</td><td>{{fixed(z.measured_mean,4)}}</td><td>{{z.before_mean!==undefined?fixed(z.before_mean,4):'—'}}</td><td>{{z.after_mean!==undefined?fixed(z.after_mean,4):'—'}}</td><td>{{z.achievable_min!==undefined?fixed(z.achievable_min,4)+'—'+fixed(z.achievable_max,4):'—'}}</td></tr>
    </tbody></table></div>
    <div v-if="historyRow.payload?.points?.length" class="table-wrap"><table><thead><tr><th>待估点</th><th>原推断%</th><th>该版本校正值%</th><th>改变量 pp</th><th>状态</th></tr></thead><tbody>
      <tr v-for="p in historyRow.payload.points" :key="p.query_id"><td>{{p.query_id}}</td><td>{{fixed(p.before,4)}}</td><td>{{fixed(p.after,4)}}</td><td>{{fixed(p.change,4)}}</td><td>{{p.locked?'零方差锁定':'自由校正'}}</td></tr>
    </tbody></table></div>
  </div>
</details>
</template>
