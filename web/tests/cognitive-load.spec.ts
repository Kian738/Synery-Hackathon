import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const campus = '/?building=proc-campus-dev-000';

test('first use discloses default start and groups optional tools and examples', async ({page}, info) => {
  await page.goto(campus);
  await expect(page.getByText('Entrance used as start. Change it if you’re elsewhere.')).toBeVisible();
  await expect(page.getByRole('button', {name: 'Scenarios', exact: true})).toBeHidden();
  await expect(page.locator('canvas')).toHaveAttribute('data-scene-painted', 'true');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const shortcut = await page.locator('.destination-shortcuts button').last().boundingBox();
  const composer = await page.getByRole('textbox', {name:'Message'}).boundingBox();
  expect(shortcut && composer && shortcut.y + shortcut.height <= composer.y).toBe(true);
  const folder=path.resolve('../runs/ux-cognitive-load');await fs.mkdir(folder,{recursive:true});
  await page.screenshot({path:path.join(folder, `${info.project.name}-first-use.png`)});
  const tools = page.getByLabel('Building tools', {exact: true});
  await tools.focus(); await tools.press('Enter');
  await expect(page.getByRole('button', {name: 'Scenarios', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Phone companion', exact: true})).toBeVisible();
  await tools.press('Escape');
  await expect(tools).toBeFocused();
  await expect(page.getByRole('button', {name: 'Scenarios', exact: true})).toBeHidden();
  const examples = page.locator('.example-requests');
  await expect(examples.locator('li').first()).toBeHidden();
  await examples.locator('summary').click();
  await expect(examples.locator('li').first()).toBeVisible();
  await examples.locator('summary').click();
});

test('room search reports omitted matches and distinguishes manual and linked origins', async ({page}) => {
  await page.goto(campus);
  await page.getByRole('button', {name:/Starting from/}).click();
  const search=page.getByRole('textbox', {name:'Search for your room'});
  await search.fill('  Floor 2  ');
  await expect(page.getByRole('status').filter({hasText:'matching rooms'})).toContainText(/Showing 8 of \d+. Keep typing/);
  await search.fill('  Lab 2.17  ');
  await page.getByRole('button', {name:/Lab 2.17.*Floor 2/}).click();
  await expect(page.getByText('Start set by you. Location is not tracked.')).toBeVisible();
  await page.getByRole('button', {name:/Starting from/}).click();
  await search.fill('zzzz-no-room');
  await expect(page.getByText('No room matches that.')).toBeVisible();
  await search.fill('Main lobby');
  await page.getByRole('button', {name:/Main lobby.*Ground floor/}).click();
  await page.getByRole('button', {name:'Toilets', exact:true}).first().click();
  await expect(page.getByRole('region', {name:'Route'})).toContainText(/Toilet/);
  await page.goto(`${campus}&at=proc-campus-dev-000-F2-S017`);
  await expect(page.getByText('Start supplied by link. Change it if you’re elsewhere.')).toBeVisible();
});
