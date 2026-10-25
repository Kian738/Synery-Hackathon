import {test,expect} from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs/promises';

test('import requires a measured dimension and exposes unverified draft fields',async({page},info)=>{
  await page.route('**/api/build',async route=>{
    expect(route.request().postDataBuffer()?.toString()).toContain('20');
    await route.fulfill({contentType:'application/json',body:JSON.stringify({building_id:'proc-campus-dev-000',report:{status:'draft',review_required:true,warnings:['Floor 1: no common labelled core; alignment is unverified.'],inferred_fields:['Opening widths are unverified.']}})});
  });
  await page.goto('/?building=proc-campus-dev-000&import=1');
  const dialog=page.getByRole('dialog',{name:'Import floor plans'});
  const width=dialog.getByRole('spinbutton',{name:'First plan width (metres)'});
  await expect(width).toHaveValue('');
  await dialog.getByLabel('Floor-plan images').setInputFiles(path.resolve('../docs/industrial-agents-hackathon-2026/data/dev/proc-campus-dev-000/floor_0_plain.png'));
  await expect(dialog.getByRole('button',{name:'Build draft'})).toBeDisabled();
  await width.fill('20');
  await dialog.getByRole('button',{name:'Build draft'}).click();
  await expect(dialog.getByLabel('Import review needed',{exact:true})).toContainText('alignment is unverified');
  await dialog.getByText('What needs verification',{exact:true}).click();
  await expect(dialog.getByText('Opening widths are unverified.',{exact:true})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Open draft for review'})).toBeVisible();
  const out=path.resolve('../runs/reconstruction-review');await fs.mkdir(out,{recursive:true});
  await page.screenshot({path:path.join(out,info.project.name+'-review.png')});
  await dialog.getByRole('button',{name:'Open draft for review'}).click();
  await expect(dialog).toHaveCount(0);
});
