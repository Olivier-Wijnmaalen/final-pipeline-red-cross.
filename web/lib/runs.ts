import { randomBytes } from "crypto";
import { mkdir, readFile, writeFile, copyFile } from "fs/promises";
import path from "path";

export const MAX_UPLOAD_BYTES=25*1024*1024;
export const allowedExtensions=new Set([".pdf",".docx",".md",".markdown"]);
export const RUN_STATES=["Uploaded","Preparing document","Extracting evidence","Validating evidence","Building evidence bank","Scoring indicators","Building dashboard","Complete","Failed"] as const;
export type AssessmentMode="document_only"|"baseline_plus_document";
export function parseMode(value:FormDataEntryValue|null):AssessmentMode{return value==="baseline_plus_document"?"baseline_plus_document":"document_only";}
export function safeRunId(id:string){if(!/^dema-[a-f0-9]{24}$/.test(id)) throw new Error("Invalid run ID"); return id;}
export function runsRoot(){return path.resolve(process.env.DEMA_RUNS_DIR || (process.env.VERCEL?"/tmp/dema-runs":path.join(process.cwd(),"..","runs")));}
export function runPath(id:string,...parts:string[]){return path.join(runsRoot(),safeRunId(id),...parts);}
export function safeFilename(name:string){const ext=path.extname(name).toLowerCase(); if(!allowedExtensions.has(ext)) throw new Error("Use a PDF, DOCX, or Markdown file"); const base=path.basename(name,ext).replace(/[^a-zA-Z0-9._-]+/g,"_").replace(/^\.+/,"").slice(0,80)||"document"; return base+ext;}
export function validateUpload(file:File){if(file.size<1) throw new Error("The uploaded file is empty"); if(file.size>MAX_UPLOAD_BYTES) throw new Error("The file exceeds the 25 MB limit"); return safeFilename(file.name);}
export async function newRun(){const id=`dema-${randomBytes(12).toString("hex")}`; await mkdir(runPath(id,"upload"),{recursive:true}); return id;}
export async function readJson(file:string){return JSON.parse(await readFile(file,"utf8"));}
export async function writeJson(file:string,value:unknown){await mkdir(path.dirname(file),{recursive:true}); await writeFile(file,JSON.stringify(value,null,2)+"\n","utf8");}
export const artifactMap={evidence:"combined_evidence_bank.json",score:"stage2/final_score.validated.json",manifest:"manifest.json",dashboard:"dashboard-data.json"} as const;
export async function copySample(id:string){const sample=path.resolve(process.cwd(),"..","examples","synthetic"); await mkdir(runPath(id,"stage2"),{recursive:true}); await copyFile(path.join(sample,"dashboard-data.json"),runPath(id,"dashboard-data.json")); await copyFile(path.join(sample,"base_evidence_bank.json"),runPath(id,"combined_evidence_bank.json")); await copyFile(path.join(sample,"expected","final_score.validated.json"),runPath(id,"stage2","final_score.validated.json")); const dashboard=await readJson(runPath(id,"dashboard-data.json")); await writeJson(runPath(id,"manifest.json"),{run_id:id,status:"complete",assessment_mode:"document_only",sample:true}); dashboard.run.run_id=id; await writeJson(runPath(id,"dashboard-data.json"),dashboard); await writeJson(runPath(id,"status.json"),{run_id:id,state:"Complete",sample:true});}
