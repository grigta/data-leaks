import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { fail } from '@sveltejs/kit';
import { z } from 'zod';
import type { PageServerLoad, Actions } from './$types';

const registerSchema = z.object({
	// Регистрация не требует полей ввода, но создадим пустую схему для совместимости
});

export const load: PageServerLoad = async () => {
	const form = await superValidate(null, zod(registerSchema), { id: 'register' });
	return { form };
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await superValidate(request, zod(registerSchema), { id: 'register' });

		if (!form.valid) {
			return fail(400, { form });
		}

		// Логика обрабатывается на клиенте
		return { form };
	}
};
