const fs=require('fs');
const items=JSON.parse(fs.readFileSync(__dirname+'/hubspot-sample.json')).map(j=>({json:j}));
const fn=new Function('$input',fs.readFileSync(__dirname+'/map.js','utf8'));
const out=fn({all:()=>items})[0].json;
const exp=[
 {hubspot_id:'101',lead_source:'Signal-led',is_closed:true,is_won:true,amount_eur:8000,days_to_close:40,period:'After signals'},
 {hubspot_id:'102',lead_source:'Generic outbound',is_closed:true,is_won:false,amount_eur:5000,days_to_close:50,period:'Before signals'},
 {hubspot_id:'103',lead_source:'Inbound',is_closed:false,is_won:false,amount_eur:0,days_to_close:null,period:'After signals'},
 {hubspot_id:'104',lead_source:'Generic outbound',is_closed:true,is_won:true,amount_eur:4200,days_to_close:30,period:'Before signals'}];
let bad=0;out.rows.forEach((r,i)=>{for(const k in exp[i]) if(r[k]!==exp[i][k]){bad++;console.log('MISMATCH',i,k,r[k],exp[i][k])}});
console.log(out.count,'rows',bad?'FAIL':'all fields match');process.exit(bad?1:0);
