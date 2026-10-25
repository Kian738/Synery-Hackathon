import {test,expect} from '@playwright/test';
// Prepared for the approved browser path; do not bypass a saved permission denial.
test('tied room references open the right floor with a compact inspector',async({page})=>{
 await page.route('**/api/sessions/*/chat',route=>route.fulfill({contentType:'text/event-stream',body:[{type:'reply',data:{text:'**287 chairs** in total.\n\n- Floor 1: Meeting rooms **1.12** and **1.22** are tied at 10 each.\n- Floor 3: Seminar rooms 3.12 and **3.26** are tied at 11 each.',model:'fixture',usage:{}}},{type:'done',data:null}].map(e=>`data: ${JSON.stringify(e)}\n\n`).join('')}));
 await page.goto('/?building=proc-campus-dev-000');await page.getByRole('textbox',{name:'Message'}).fill('Which rooms have the most chairs on each floor?');await page.getByRole('button',{name:'Send',exact:true}).click();
 await expect(page.locator('.agent-reply ul li')).toHaveCount(2);
 await page.getByRole('button',{name:'1.12',exact:true}).click();
 const room=page.getByRole('dialog',{name:'Meeting room 1.12',exact:true});await expect(room).toBeVisible();await expect(room.getByText('Floor 1',{exact:false})).toBeVisible();
 await expect(room.locator('.room-card-details')).not.toHaveAttribute('open','');
 await room.getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('button',{name:'1.22',exact:true}).click();await expect(page.getByRole('dialog',{name:'Meeting room 1.22',exact:true})).toBeVisible();
 const overflow=await page.locator('.chat-workspace').evaluate(el=>el.scrollWidth>el.clientWidth+1);expect(overflow).toBe(false);
});
