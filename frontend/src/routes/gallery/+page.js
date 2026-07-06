import { redirect } from '@sveltejs/kit';
import { getInventory, getSession } from '$lib/api.js';

export async function load({ fetch }) {
	const inventory = await getInventory(fetch);
	if (!inventory) throw redirect(307, '/');
	const session = await getSession(fetch);
	return { inventory, displayName: session?.display_name ?? '' };
}
