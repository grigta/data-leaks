<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import Bot from '@lucide/svelte/icons/bot';
	import DollarSign from '@lucide/svelte/icons/dollar-sign';
	import Zap from '@lucide/svelte/icons/zap';
	import User from '@lucide/svelte/icons/user';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
</script>

<svelte:head>
	<title>Telegram Бот - Инструкция</title>
</svelte:head>

<div class="max-w-4xl mx-auto space-y-6">
	<!-- Header Card -->
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center gap-3 text-2xl">
				<MessageCircle class="h-7 w-7" />
				Пробив через Telegram бота
			</CardTitle>
		</CardHeader>
		<CardContent>
			<p class="text-muted-foreground">
				Пошаговая инструкция по использованию Telegram бота для поиска SSN данных.
			</p>
		</CardContent>
	</Card>

	<!-- Steps 1-5 -->
	<ol class="space-y-6 list-none p-0 m-0">
		<!-- Step 1: Add bot to chat -->
		<li>
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">1</span>
						Добавьте бота в групповой чат
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<p>
						Создайте групповой чат в Telegram и добавьте бота как участника.
						Рекомендуется сделать бота администратором чата для корректной работы.
					</p>
					<div class="flex items-start gap-2 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
						<AlertCircle class="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
						<p class="text-sm text-amber-500">
							Бот работает только в групповых чатах, не в личных сообщениях.
						</p>
					</div>
				</CardContent>
			</Card>
		</li>

		<!-- Step 2: Login -->
		<li>
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">2</span>
						Активируйте бота с помощью команды /login
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<p>
						Используйте ваш access code для активации бота в чате:
					</p>
					<pre class="bg-muted p-4 rounded-lg overflow-x-auto"><code class="text-sm">/login XXX-XXX-XXX-XXX</code></pre>
					<p class="text-sm text-muted-foreground">
						Access code можно найти в профиле на сайте. Перейдите в раздел
						<a href="/dashboard" class="text-primary hover:underline">Dashboard</a>
						для получения кода.
					</p>
				</CardContent>
			</Card>
		</li>

		<!-- Step 3: Select mode -->
		<li>
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">3</span>
						Выберите режим поиска через команду /mode
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<p>
						Перед отправкой данных необходимо выбрать режим поиска:
					</p>
					<pre class="bg-muted p-4 rounded-lg overflow-x-auto"><code class="text-sm">/mode</code></pre>

					<div class="space-y-4 mt-4">
						<!-- Instant SSN -->
						<div class="flex items-start gap-3 p-4 rounded-lg border">
							<Zap class="h-5 w-5 text-yellow-500 mt-0.5 flex-shrink-0" />
							<div class="space-y-1">
								<div class="flex items-center gap-2">
									<span class="font-semibold">Instant SSN</span>
									<Badge variant="secondary">$2</Badge>
								</div>
								<p class="text-sm text-muted-foreground">
									Мгновенный поиск SSN. Списание $2 только при успешном результате.
								</p>
							</div>
						</div>

						<!-- Manual SSN -->
						<div class="flex items-start gap-3 p-4 rounded-lg border">
							<User class="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
							<div class="space-y-1">
								<div class="flex items-center gap-2">
									<span class="font-semibold">Manual SSN</span>
									<Badge variant="secondary">$3</Badge>
								</div>
								<p class="text-sm text-muted-foreground">
									Создание тикета для ручной обработки воркерами. Стоимость: $3 за запрос.
								</p>
							</div>
						</div>

						<!-- Hybrid -->
						<div class="flex items-start gap-3 p-4 rounded-lg border">
							<RefreshCw class="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
							<div class="space-y-1">
								<div class="flex items-center gap-2">
									<span class="font-semibold">Hybrid</span>
									<Badge variant="outline">авто</Badge>
								</div>
								<p class="text-sm text-muted-foreground">
									Сначала пытается instant поиск ($2 при успехе).
									Если SSN не найден → автоматически создаёт manual тикет ($3).
								</p>
							</div>
						</div>
					</div>
				</CardContent>
			</Card>
		</li>

		<!-- Step 4: Send request -->
		<li>
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">4</span>
						Отправьте данные для поиска
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<p>
						Упомяните бота и укажите данные в формате:
					</p>
					<pre class="bg-muted p-4 rounded-lg overflow-x-auto"><code class="text-sm">@botname Firstname Lastname
Address</code></pre>

					<p class="text-sm font-medium mt-4">Пример:</p>
					<pre class="bg-muted p-4 rounded-lg overflow-x-auto"><code class="text-sm">@dataleaks_bot John Doe
123 Main Street, New York, NY 10001</code></pre>

					<p class="text-sm text-muted-foreground mt-2">
						Замените <code class="bg-muted px-1 rounded">@botname</code> на имя вашего бота.
					</p>
				</CardContent>
			</Card>
		</li>

		<!-- Step 5: Check balance -->
		<li>
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<span class="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-bold">5</span>
						Проверка баланса
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<p>
						Для проверки текущего баланса используйте команду:
					</p>
					<pre class="bg-muted p-4 rounded-lg overflow-x-auto"><code class="text-sm">/balance</code></pre>
				</CardContent>
			</Card>
		</li>
	</ol>

	<!-- Important info -->
	<Card class="border-primary/50">
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<AlertCircle class="h-5 w-5" />
				Важная информация
			</CardTitle>
		</CardHeader>
		<CardContent>
			<ul class="space-y-2 list-disc list-inside text-sm">
				<li>Бот работает только в групповых чатах</li>
				<li>Необходимо выбрать режим поиска перед отправкой данных</li>
				<li>Списание средств происходит автоматически при успешном поиске (instant) или создании тикета (manual)</li>
				<li>Результаты отправляются в тот же чат</li>
				<li>При недостаточном балансе запрос будет отклонён</li>
			</ul>
		</CardContent>
	</Card>

	<!-- Back button -->
	<div class="flex justify-center pt-4">
		<a
			href="/dashboard"
			class="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
		>
			Вернуться к панели
		</a>
	</div>
</div>
