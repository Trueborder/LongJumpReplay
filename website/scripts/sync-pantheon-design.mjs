import {cp,mkdir,readFile,readdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const website=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=path.join(website,'shared/pantheon');
const destinations=[path.join(website,'tomaspisar.cz/account/pantheon')];
const wikiIndex=process.argv.indexOf('--wiki');
if(wikiIndex>=0){if(!process.argv[wikiIndex+1])throw Error('--wiki requires the wiki checkout path');destinations.push(path.resolve(process.argv[wikiIndex+1],'assets/pantheon'));}
if(!process.argv.includes('--check'))for(const destination of destinations){await mkdir(destination,{recursive:true});await cp(source,destination,{recursive:true});console.log('Synced Pantheon design assets: '+destination);}
if(process.argv.includes('--check'))for(const destination of destinations)for(const file of await readdir(source)){
 if(!(await readFile(path.join(source,file))).equals(await readFile(path.join(destination,file))))throw Error('Asset mismatch: '+file);
}
