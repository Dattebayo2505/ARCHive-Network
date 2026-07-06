import { redirect } from '@sveltejs/kit';
import { getInventory } from '$lib/api.js';

export async function load({ fetch }) {
	const inventory = await getInventory(fetch);
	if (!inventory) throw redirect(307, '/');
	return { inventory };
}
