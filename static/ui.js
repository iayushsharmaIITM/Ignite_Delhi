/* Shared UI preferences: language + theme. Loaded on every page BEFORE
 * shell.js so the theme attribute is set before first paint (no flash) and
 * the sidebar can build itself in the chosen language.
 *
 *   KI18N.t(key, fallback)   translate; falls back to English, then the key
 *   KI18N.apply(root)        rewrite [data-i18n] text, [data-i18n-ph]
 *                            placeholders and [data-i18n-title] titles
 *   KI18N.setLang(code)      persist + re-apply + fire 'kestrel:lang'
 *   KTheme.set(mode)         'system' | 'dark' | 'light' — persists,
 *                            sets html[data-theme], fires 'kestrel:theme'
 *
 * Language and theme survive reloads (localStorage), and 'system' follows
 * the OS live via prefers-color-scheme.
 */
(function () {
  // ------------------------------------------------------------------ dict
  const DICT = {
    en: {
      'nav.workspace': 'Workspace', 'nav.ask': 'Ask', 'nav.new_brain': 'New brain',
      'nav.brains': 'Brains', 'nav.graph': 'Graph', 'nav.chats': 'Chats',
      'nav.new_chat': 'New chat', 'nav.no_chats': 'No saved chats yet',
      'sb.connecting': 'connecting…', 'sb.key_rejected': '· key rejected',
      'sb.unreachable': 'unreachable', 'brain.demo': 'Demo brain',

      'greet.morning': 'Morning, how can I help?',
      'greet.afternoon': 'Afternoon, how can I help?',
      'greet.evening': 'Evening, how can I help?',

      'composer.placeholder': 'Ask across every document the company has written…',
      'composer.placeholder_brain': 'Ask across the documents you uploaded…',
      'menu.questions': '{n} questions',
      'composer.switch_brain': 'Switch brain', 'composer.actions': 'Conversation actions',
      'composer.attach': 'Attach files to this message', 'composer.send': 'Send',
      'composer.stop': 'Stop generating',

      'menu.turns': '{n} turns', 'menu.copy_transcript': 'Copy transcript',
      'menu.add_docs': 'Add documents to this brain…', 'menu.export_md': 'Export Markdown',
      'menu.export_txt': 'Export plain text', 'menu.export_docx': 'Export Word document',
      'menu.export_pdf': 'Export PDF', 'menu.clear_chat': 'Clear conversation',

      'files.title': 'Add documents', 'files.drop': 'Drop files here or choose files',
      'files.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, code files · up to 5 MB each · 40 max. Added straight into this brain — no restart, immediately answerable.',
      'files.add': 'Add to brain', 'files.close': 'Close', 'files.choose': 'choose files',
      'src.copy': 'Copy', 'src.close': 'Close',
      'src.open': 'Open this source document',

      'chip.demo1': 'Why is the Bluepeak renewal at risk?',
      'chip.demo2': 'What credit do we owe, and who approved it?',
      'chip.demo3': 'Who owns the renewal and the RCA?',
      'chip.demo4': 'Is the renewal date consistent?',
      'chip.gen1': 'Summarise what is in this brain',
      'chip.gen2': 'What are the next steps?',
      'chip.gen3': 'Draft a mail from the latest answer',
      'chip.gen4': 'Is everything consistent?',

      'gate.title': 'Sign in to Kestrel',
      'up.h1': 'Build a company brain',
      'up.sub': 'Upload your own documents. Each file is read, chunked and turned into a knowledge graph — then you query it in the same dashboard as the demo brain.',
      'up.label_name': 'Brain name', 'up.name_ph': 'e.g. acme_contracts',
      'up.name_hint': 'Letters, numbers and underscores, 3–40 characters. Spaces become underscores.',
      'up.label_docs': 'Documents', 'up.drop': 'Drop files here', 'up.choose': 'choose files',
      'up.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, code files (.py, .yaml, …) · up to 5 MB each · 40 max',
      'up.build': 'Build brain', 'up.label_ing': 'Ingestion',
      'graph.title': 'Knowledge graph',
      'gate.sub': "Your company's answers, grounded in your documents.",

      'set.language': 'Language', 'set.theme': 'App theme', 'set.usage': 'Usage stats',
      'set.upgrade': 'Upgrade', 'set.account': 'Manage account', 'set.signout': 'Disconnect',
      'set.sign_in': 'Sign in', 'set.system': 'System default', 'set.dark': 'Dark theme',
      'set.light': 'Light theme',

      'view.title': 'View', 'view.sort_by': 'Sort by', 'view.by_brain': 'By brain',
      'view.timeline': 'Timeline', 'view.updated': 'Updated', 'view.created': 'Created',
      'view.grouped': 'Grouped by brain', 'view.sorted': 'sorted by',
      'view.toggle': 'View and sort',

      'usage.title': 'Usage stats', 'usage.sub': 'Last 30 days · estimated tokens',
      'usage.feature': 'Feature', 'usage.brain': 'Brain', 'usage.model': 'Model',
      'usage.calls': 'Calls', 'usage.tokens': 'Tokens', 'usage.time': 'Time',
      'usage.empty': 'No model calls recorded yet.', 'usage.signin': 'Sign in to see usage.',

      'up.title': 'Upgrade Kestrel',
      'up.sub': 'Simple plans that scale with your company brain.',
      'up.current': 'Current plan', 'up.soon': 'Coming soon', 'up.per_mo': '/mo',
      'up.free': 'Free', 'up.pro': 'Pro', 'up.biz': 'Business',
      'up.free_f1': '1 brain, up to 3 members', 'up.free_f2': '200 answers a month',
      'up.free_f3': 'All export formats',
      'up.pro_f1': 'Unlimited brains and members', 'up.pro_f2': 'Unlimited answers',
      'up.pro_f3': 'Priority models, longer context',
      'up.biz_f1': 'Org workspaces with roles', 'up.biz_f2': 'SSO and audit trail',
      'up.biz_f3': 'Priority support',
      'up.note': 'Checkout activates as soon as plans are published in billing. Everything you use today stays free.',

      'stage.smalltalk': 'Direct chat — no retrieval needed',
      'stage.plan': 'Planning retrieval agents',
      'stage.router_chat': 'General chat — bypassing retrieval',
      'stage.delegating': 'Delegating to retrieval agents',
    },

    hi: {
      'nav.workspace': 'वर्कस्पेस', 'nav.ask': 'पूछें', 'nav.new_brain': 'नया ब्रेन',
      'nav.brains': 'ब्रेन्स', 'nav.graph': 'ग्राफ़', 'nav.chats': 'चैट',
      'nav.new_chat': 'नई चैट', 'nav.no_chats': 'अभी कोई चैट सहेजी नहीं गई',
      'sb.connecting': 'कनेक्ट हो रहा है…', 'sb.key_rejected': '· कुंजी अस्वीकृत',
      'sb.unreachable': 'पहुँच से बाहर', 'brain.demo': 'डेमो ब्रेन',

      'greet.morning': 'सुप्रभात, मैं आपकी कैसे मदद करूँ?',
      'greet.afternoon': 'नमस्कार, मैं आपकी कैसे मदद करूँ?',
      'greet.evening': 'शुभ संध्या, मैं आपकी कैसे मदद करूँ?',

      'composer.placeholder': 'कंपनी के हर दस्तावेज़ से पूछें…',
      'composer.placeholder_brain': 'आपके अपलोड किए दस्तावेज़ों से पूछें…',
      'menu.questions': '{n} प्रश्न',
      'composer.switch_brain': 'ब्रेन बदलें', 'composer.actions': 'चैट क्रियाएँ',
      'composer.attach': 'इस संदेश में फ़ाइलें जोड़ें', 'composer.send': 'भेजें',
      'composer.stop': 'जवाब रोकें',

      'menu.turns': '{n} बातचीत', 'menu.copy_transcript': 'पूरी बातचीत कॉपी करें',
      'menu.add_docs': 'इस ब्रेन में दस्तावेज़ जोड़ें…', 'menu.export_md': 'मार्कडाउन निर्यात करें',
      'menu.export_txt': 'सादा टेक्स्ट निर्यात करें', 'menu.export_docx': 'वर्ड डॉक्यूमेंट निर्यात करें',
      'menu.export_pdf': 'PDF निर्यात करें', 'menu.clear_chat': 'बातचीत साफ़ करें',

      'files.title': 'दस्तावेज़ जोड़ें', 'files.drop': 'फ़ाइलें यहाँ छोड़ें या चुनें',
      'files.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, कोड फ़ाइलें · प्रत्येक 5 MB तक · अधिकतम 40। सीधे इस ब्रेन में जुड़ें — रीस्टार्ट नहीं, तुरंत उत्तर योग्य।',
      'files.add': 'ब्रेन में जोड़ें', 'files.close': 'बंद करें', 'files.choose': 'फ़ाइलें चुनें',
      'src.copy': 'कॉपी', 'src.close': 'बंद करें',
      'src.open': 'यह स्रोत दस्तावेज़ खोलें',

      'chip.demo1': 'ब्लूपीक नवीनीकरण जोखिम में क्यों है?',
      'chip.demo2': 'हमें कौन-सा क्रेडिट देना है, और किसने मंज़ूरी दी?',
      'chip.demo3': 'नवीनीकरण और RCA का मालिक कौन है?',
      'chip.demo4': 'क्या नवीनीकरण तिथि सुसंगत है?',
      'chip.gen1': 'इस ब्रेन में जो है उसका सारांश दें',
      'chip.gen2': 'अगले कदम क्या हैं?',
      'chip.gen3': 'आख़िरी जवाब से एक मेल बनाएँ',
      'chip.gen4': 'क्या सब कुछ आपस में सुसंगत है?',

      'gate.title': 'Kestrel में साइन इन करें',
      'up.h1': 'कंपनी ब्रेन बनाएँ',
      'up.sub': 'अपने दस्तावेज़ अपलोड करें। हर फ़ाइल पढ़ी, खंडित और ज्ञान-ग्राफ़ में बदली जाती है — फिर आप उसे डेमो ब्रेन वाले ही डैशबोर्ड से पूछते हैं।',
      'up.label_name': 'ब्रेन नाम', 'up.name_ph': 'जैसे acme_contracts',
      'up.name_hint': 'अक्षर, संख्याएँ और अंडरस्कोर, 3–40 अक्षर। स्पेस अंडरस्कोर बन जाते हैं।',
      'up.label_docs': 'दस्तावेज़', 'up.drop': 'फ़ाइलें यहाँ छोड़ें', 'up.choose': 'फ़ाइलें चुनें',
      'up.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, कोड फ़ाइलें (.py, .yaml, …) · प्रत्येक 5 MB तक · अधिकतम 40',
      'up.build': 'ब्रेन बनाएँ', 'up.label_ing': 'इनजेशन',
      'graph.title': 'ज्ञान ग्राफ़',
      'gate.sub': 'आपकी कंपनी के जवाब, आपके दस्तावेज़ों पर आधारित।',

      'set.language': 'भाषा', 'set.theme': 'ऐप थीम', 'set.usage': 'उपयोग आँकड़े',
      'set.upgrade': 'अपग्रेड', 'set.account': 'खाता प्रबंधन', 'set.signout': 'डिस्कनेक्ट',
      'set.sign_in': 'साइन इन', 'set.system': 'सिस्टम डिफ़ॉल्ट', 'set.dark': 'डार्क थीम',
      'set.light': 'लाइट थीम',

      'view.title': 'दृश्य', 'view.sort_by': 'क्रम', 'view.by_brain': 'ब्रेन के अनुसार',
      'view.timeline': 'समयरेखा', 'view.updated': 'अपडेट', 'view.created': 'निर्माण',
      'view.grouped': 'ब्रेन के अनुसार समूहित', 'view.sorted': 'क्रम:',
      'view.toggle': 'दृश्य और क्रम',

      'usage.title': 'उपयोग आँकड़े', 'usage.sub': 'पिछले 30 दिन · अनुमानित टोकन',
      'usage.feature': 'फ़ीचर', 'usage.brain': 'ब्रेन', 'usage.model': 'मॉडल',
      'usage.calls': 'कॉल', 'usage.tokens': 'टोकन', 'usage.time': 'समय',
      'usage.empty': 'अभी कोई मॉडल कॉल दर्ज नहीं हुई।', 'usage.signin': 'उपयोग देखने के लिए साइन इन करें।',

      'up.title': 'Kestrel अपग्रेड करें',
      'up.sub': 'आपके कंपनी ब्रेन के साथ बढ़ने वाली सरल योजनाएँ।',
      'up.current': 'वर्तमान योजना', 'up.soon': 'जल्द आ रहा है', 'up.per_mo': '/माह',
      'up.free': 'फ्री', 'up.pro': 'प्रो', 'up.biz': 'बिज़नेस',
      'up.free_f1': '1 ब्रेन, 3 सदस्यों तक', 'up.free_f2': 'महीने में 200 जवाब',
      'up.free_f3': 'सभी निर्यात प्रारूप',
      'up.pro_f1': 'असीमित ब्रेन और सदस्य', 'up.pro_f2': 'असीमित जवाब',
      'up.pro_f3': 'प्राथमिकता मॉडल, लंबा संदर्भ',
      'up.biz_f1': 'भूमिकाओं वाले ऑर्ग वर्कस्पेस', 'up.biz_f2': 'SSO और ऑडिट ट्रेल',
      'up.biz_f3': 'प्राथमिकता सहायता',
      'up.note': 'बिलिंग में योजनाएँ प्रकाशित होते ही चेकआउट सक्रिय हो जाएगा। आज आप जो भी उपयोग करते हैं वह मुफ़्त रहेगा।',

      'stage.smalltalk': 'सीधी चैट — रिट्रीवल की ज़रूरत नहीं',
      'stage.plan': 'रिट्रीवल एजेंट्स की योजना',
      'stage.router_chat': 'सामान्य चैट — रिट्रीवल छोड़ा गया',
      'stage.delegating': 'रिट्रीवल एजेंट्स को सौंपा गया',
    },

    es: {
      'nav.workspace': 'Espacio', 'nav.ask': 'Preguntar', 'nav.new_brain': 'Nuevo cerebro',
      'nav.brains': 'Cerebros', 'nav.graph': 'Grafo', 'nav.chats': 'Chats',
      'nav.new_chat': 'Nuevo chat', 'nav.no_chats': 'Aún no hay chats guardados',
      'sb.connecting': 'conectando…', 'sb.key_rejected': '· clave rechazada',
      'sb.unreachable': 'inaccesible', 'brain.demo': 'Cerebro de demostración',

      'greet.morning': 'Buenos días, ¿en qué puedo ayudarte?',
      'greet.afternoon': 'Buenas tardes, ¿en qué puedo ayudarte?',
      'greet.evening': 'Buenas noches, ¿en qué puedo ayudarte?',

      'composer.placeholder': 'Pregunta en todos los documentos de la empresa…',
      'composer.placeholder_brain': 'Pregunta en los documentos que subiste…',
      'menu.questions': '{n} preguntas',
      'composer.switch_brain': 'Cambiar cerebro', 'composer.actions': 'Acciones de la conversación',
      'composer.attach': 'Adjuntar archivos a este mensaje', 'composer.send': 'Enviar',
      'composer.stop': 'Dejar de generar',

      'menu.turns': '{n} turnos', 'menu.copy_transcript': 'Copiar la conversación',
      'menu.add_docs': 'Añadir documentos a este cerebro…', 'menu.export_md': 'Exportar Markdown',
      'menu.export_txt': 'Exportar texto plano', 'menu.export_docx': 'Exportar documento Word',
      'menu.export_pdf': 'Exportar PDF', 'menu.clear_chat': 'Borrar conversación',

      'files.title': 'Añadir documentos', 'files.drop': 'Suelta archivos aquí o elígelos',
      'files.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, código · hasta 5 MB cada uno · 40 máx. Se añaden a este cerebro — sin reinicio, respondibles al instante.',
      'files.add': 'Añadir al cerebro', 'files.close': 'Cerrar', 'files.choose': 'elegir archivos',
      'src.copy': 'Copiar', 'src.close': 'Cerrar',
      'src.open': 'Abrir este documento fuente',

      'chip.demo1': '¿Por qué está en riesgo la renovación de Bluepeak?',
      'chip.demo2': '¿Qué crédito debemos y quién lo aprobó?',
      'chip.demo3': '¿Quién es responsable de la renovación y del RCA?',
      'chip.demo4': '¿Es coherente la fecha de renovación?',
      'chip.gen1': 'Resumen de lo que hay en este cerebro',
      'chip.gen2': '¿Cuáles son los siguientes pasos?',
      'chip.gen3': 'Redacta un correo con la última respuesta',
      'chip.gen4': '¿Todo es coherente entre sí?',

      'gate.title': 'Inicia sesión en Kestrel',
      'up.h1': 'Construye un cerebro de empresa',
      'up.sub': 'Sube tus propios documentos. Cada archivo se lee, se divide y se convierte en un grafo de conocimiento — luego lo consultas en el mismo panel que el cerebro de demostración.',
      'up.label_name': 'Nombre del cerebro', 'up.name_ph': 'p. ej. acme_contracts',
      'up.name_hint': 'Letras, números y guiones bajos, 3–40 caracteres. Los espacios se convierten en guiones bajos.',
      'up.label_docs': 'Documentos', 'up.drop': 'Suelta archivos aquí', 'up.choose': 'elegir archivos',
      'up.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, código (.py, .yaml, …) · hasta 5 MB cada uno · 40 máx',
      'up.build': 'Construir cerebro', 'up.label_ing': 'Ingesta',
      'graph.title': 'Grafo de conocimiento',
      'gate.sub': 'Las respuestas de tu empresa, basadas en tus documentos.',

      'set.language': 'Idioma', 'set.theme': 'Tema', 'set.usage': 'Estadísticas de uso',
      'set.upgrade': 'Mejorar plan', 'set.account': 'Gestionar cuenta', 'set.signout': 'Desconectar',
      'set.sign_in': 'Iniciar sesión', 'set.system': 'Predeterminado del sistema',
      'set.dark': 'Tema oscuro', 'set.light': 'Tema claro',

      'view.title': 'Vista', 'view.sort_by': 'Ordenar por', 'view.by_brain': 'Por cerebro',
      'view.timeline': 'Cronología', 'view.updated': 'Actualización', 'view.created': 'Creación',
      'view.grouped': 'Agrupado por cerebro', 'view.sorted': 'ordenado por',
      'view.toggle': 'Ver y ordenar',

      'usage.title': 'Estadísticas de uso', 'usage.sub': 'Últimos 30 días · tokens estimados',
      'usage.feature': 'Función', 'usage.brain': 'Cerebro', 'usage.model': 'Modelo',
      'usage.calls': 'Llamadas', 'usage.tokens': 'Tokens', 'usage.time': 'Tiempo',
      'usage.empty': 'Aún no hay llamadas al modelo.', 'usage.signin': 'Inicia sesión para ver el uso.',

      'up.title': 'Mejora Kestrel',
      'up.sub': 'Planes simples que crecen con el cerebro de tu empresa.',
      'up.current': 'Plan actual', 'up.soon': 'Próximamente', 'up.per_mo': '/mes',
      'up.free': 'Gratis', 'up.pro': 'Pro', 'up.biz': 'Empresa',
      'up.free_f1': '1 cerebro, hasta 3 miembros', 'up.free_f2': '200 respuestas al mes',
      'up.free_f3': 'Todos los formatos de exportación',
      'up.pro_f1': 'Cerebros y miembros ilimitados', 'up.pro_f2': 'Respuestas ilimitadas',
      'up.pro_f3': 'Modelos prioritarios, contexto largo',
      'up.biz_f1': 'Espacios de organización con roles', 'up.biz_f2': 'SSO y auditoría',
      'up.biz_f3': 'Soporte prioritario',
      'up.note': 'El pago se activa en cuanto se publiquen los planes. Todo lo que uses hoy sigue siendo gratis.',

      'stage.smalltalk': 'Chat directo — sin recuperación',
      'stage.plan': 'Planificando agentes de recuperación',
      'stage.router_chat': 'Chat general — sin recuperación',
      'stage.delegating': 'Delegando en agentes de recuperación',
    },

    fr: {
      'nav.workspace': 'Espace', 'nav.ask': 'Demander', 'nav.new_brain': 'Nouveau cerveau',
      'nav.brains': 'Cerveaux', 'nav.graph': 'Graphe', 'nav.chats': 'Conversations',
      'nav.new_chat': 'Nouvelle conversation', 'nav.no_chats': 'Aucune conversation enregistrée',
      'sb.connecting': 'connexion…', 'sb.key_rejected': '· clé rejetée',
      'sb.unreachable': 'injoignable', 'brain.demo': 'Cerveau de démo',

      'greet.morning': 'Bonjour, comment puis-je aider ?',
      'greet.afternoon': 'Bon après-midi, comment puis-je aider ?',
      'greet.evening': 'Bonsoir, comment puis-je aider ?',

      'composer.placeholder': 'Posez vos questions sur tous les documents de l’entreprise…',
      'composer.placeholder_brain': 'Interrogez les documents que vous avez téléversés…',
      'menu.questions': '{n} questions',
      'composer.switch_brain': 'Changer de cerveau', 'composer.actions': 'Actions de la conversation',
      'composer.attach': 'Joindre des fichiers à ce message', 'composer.send': 'Envoyer',
      'composer.stop': 'Arrêter la génération',

      'menu.turns': '{n} tours', 'menu.copy_transcript': 'Copier la conversation',
      'menu.add_docs': 'Ajouter des documents à ce cerveau…', 'menu.export_md': 'Exporter en Markdown',
      'menu.export_txt': 'Exporter en texte brut', 'menu.export_docx': 'Exporter en document Word',
      'menu.export_pdf': 'Exporter en PDF', 'menu.clear_chat': 'Effacer la conversation',

      'files.title': 'Ajouter des documents', 'files.drop': 'Déposez des fichiers ici ou choisissez-les',
      'files.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, code · 5 Mo max chacun · 40 max. Ajoutés directement à ce cerveau — sans redémarrage, exploitables immédiatement.',
      'files.add': 'Ajouter au cerveau', 'files.close': 'Fermer', 'files.choose': 'choisir des fichiers',
      'src.copy': 'Copier', 'src.close': 'Fermer',
      'src.open': 'Ouvrir ce document source',

      'chip.demo1': 'Pourquoi le renouvellement Bluepeak est-il à risque ?',
      'chip.demo2': 'Quel crédit devons-nous, et qui l’a approuvé ?',
      'chip.demo3': 'Qui est responsable du renouvellement et du RCA ?',
      'chip.demo4': 'La date de renouvellement est-elle cohérente ?',
      'chip.gen1': 'Résumer le contenu de ce cerveau',
      'chip.gen2': 'Quelles sont les prochaines étapes ?',
      'chip.gen3': 'Rédiger un mail à partir de la dernière réponse',
      'chip.gen4': 'Tout est-il cohérent entre eux ?',

      'gate.title': 'Connectez-vous à Kestrel',
      'up.h1': 'Construire un cerveau d’entreprise',
      'up.sub': 'Téléversez vos propres documents. Chaque fichier est lu, découpé et transformé en graphe de connaissances — vous l’interrogez ensuite dans le même tableau de bord que le cerveau de démo.',
      'up.label_name': 'Nom du cerveau', 'up.name_ph': 'ex. acme_contracts',
      'up.name_hint': 'Lettres, chiffres et underscores, 3–40 caractères. Les espaces deviennent des underscores.',
      'up.label_docs': 'Documents', 'up.drop': 'Déposez les fichiers ici', 'up.choose': 'choisir des fichiers',
      'up.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, code (.py, .yaml, …) · 5 Mo max chacun · 40 max',
      'up.build': 'Construire le cerveau', 'up.label_ing': 'Ingestion',
      'graph.title': 'Graphe de connaissances',
      'gate.sub': 'Les réponses de votre entreprise, ancrées dans vos documents.',

      'set.language': 'Langue', 'set.theme': 'Thème', 'set.usage': "Statistiques d'utilisation",
      'set.upgrade': 'Passer à Pro', 'set.account': 'Gérer le compte', 'set.signout': 'Se déconnecter',
      'set.sign_in': 'Se connecter', 'set.system': 'Valeur par défaut du système',
      'set.dark': 'Thème sombre', 'set.light': 'Thème clair',

      'view.title': 'Affichage', 'view.sort_by': 'Trier par', 'view.by_brain': 'Par cerveau',
      'view.timeline': 'Chronologie', 'view.updated': 'Mis à jour', 'view.created': 'Créé',
      'view.grouped': 'Groupé par cerveau', 'view.sorted': 'trié par',
      'view.toggle': 'Afficher et trier',

      'usage.title': "Statistiques d'utilisation", 'usage.sub': '30 derniers jours · tokens estimés',
      'usage.feature': 'Fonction', 'usage.brain': 'Cerveau', 'usage.model': 'Modèle',
      'usage.calls': 'Appels', 'usage.tokens': 'Tokens', 'usage.time': 'Durée',
      'usage.empty': "Aucun appel de modèle enregistré.", 'usage.signin': "Connectez-vous pour voir l'utilisation.",

      'up.title': 'Améliorer Kestrel',
      'up.sub': 'Des offres simples qui grandissent avec votre cerveau d’entreprise.',
      'up.current': 'Offre actuelle', 'up.soon': 'Bientôt disponible', 'up.per_mo': '/mois',
      'up.free': 'Gratuit', 'up.pro': 'Pro', 'up.biz': 'Entreprise',
      'up.free_f1': '1 cerveau, jusqu’à 3 membres', 'up.free_f2': '200 réponses par mois',
      'up.free_f3': 'Tous les formats d’export',
      'up.pro_f1': 'Cerveaux et membres illimités', 'up.pro_f2': 'Réponses illimitées',
      'up.pro_f3': 'Modèles prioritaires, contexte long',
      'up.biz_f1': 'Espaces d’organisation avec rôles', 'up.biz_f2': 'SSO et piste d’audit',
      'up.biz_f3': 'Support prioritaire',
      'up.note': 'Le paiement s’active dès publication des offres. Tout ce que vous utilisez aujourd’hui reste gratuit.',

      'stage.smalltalk': 'Conversation directe — sans récupération',
      'stage.plan': 'Planification des agents de récupération',
      'stage.router_chat': 'Conversation générale — sans récupération',
      'stage.delegating': 'Délégation aux agents de récupération',
    },

    de: {
      'nav.workspace': 'Arbeitsbereich', 'nav.ask': 'Fragen', 'nav.new_brain': 'Neues Brain',
      'nav.brains': 'Brains', 'nav.graph': 'Graph', 'nav.chats': 'Chats',
      'nav.new_chat': 'Neuer Chat', 'nav.no_chats': 'Noch keine gespeicherten Chats',
      'sb.connecting': 'verbinde…', 'sb.key_rejected': '· Schlüssel abgelehnt',
      'sb.unreachable': 'nicht erreichbar', 'brain.demo': 'Demo-Brain',

      'greet.morning': 'Guten Morgen, wie kann ich helfen?',
      'greet.afternoon': 'Guten Tag, wie kann ich helfen?',
      'greet.evening': 'Guten Abend, wie kann ich helfen?',

      'composer.placeholder': 'Frag alle Dokumente des Unternehmens…',
      'composer.placeholder_brain': 'Frag die hochgeladenen Dokumente…',
      'menu.questions': '{n} Fragen',
      'composer.switch_brain': 'Brain wechseln', 'composer.actions': 'Unterhaltungsaktionen',
      'composer.attach': 'Dateien an diese Nachricht anhängen', 'composer.send': 'Senden',
      'composer.stop': 'Generierung stoppen',

      'menu.turns': '{n} Runden', 'menu.copy_transcript': 'Verlauf kopieren',
      'menu.add_docs': 'Dokumente zu diesem Brain hinzufügen…', 'menu.export_md': 'Als Markdown exportieren',
      'menu.export_txt': 'Als Text exportieren', 'menu.export_docx': 'Als Word-Dokument exportieren',
      'menu.export_pdf': 'Als PDF exportieren', 'menu.clear_chat': 'Unterhaltung löschen',

      'files.title': 'Dokumente hinzufügen', 'files.drop': 'Dateien hierher ziehen oder auswählen',
      'files.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, Code · je bis 5 MB · max. 40. Landen direkt in diesem Brain — kein Neustart, sofort abfragbar.',
      'files.add': 'Zum Brain hinzufügen', 'files.close': 'Schließen', 'files.choose': 'Dateien auswählen',
      'src.copy': 'Kopieren', 'src.close': 'Schließen',
      'src.open': 'Dieses Quelldokument öffnen',

      'chip.demo1': 'Warum ist die Bluepeak-Verlängerung gefährdet?',
      'chip.demo2': 'Welches Credit schulden wir, und wer hat es genehmigt?',
      'chip.demo3': 'Wem gehören Verlängerung und RCA?',
      'chip.demo4': 'Ist das Verlängerungsdatum konsistent?',
      'chip.gen1': 'Zusammenfassen, was in diesem Brain steckt',
      'chip.gen2': 'Was sind die nächsten Schritte?',
      'chip.gen3': 'Mail aus der letzten Antwort entwerfen',
      'chip.gen4': 'Ist alles untereinander konsistent?',

      'gate.title': 'Bei Kestrel anmelden',
      'up.h1': 'Company Brain erstellen',
      'up.sub': 'Laden Sie Ihre eigenen Dokumente hoch. Jede Datei wird gelesen, in Abschnitte zerlegt und in einen Wissensgraphen verwandelt — abgefragt wird sie im selben Dashboard wie das Demo-Brain.',
      'up.label_name': 'Brain-Name', 'up.name_ph': 'z. B. acme_contracts',
      'up.name_hint': 'Buchstaben, Zahlen und Unterstriche, 3–40 Zeichen. Leerzeichen werden Unterstriche.',
      'up.label_docs': 'Dokumente', 'up.drop': 'Dateien hierher ziehen', 'up.choose': 'Dateien auswählen',
      'up.hint': 'PDF, DOCX, TXT, MD, CSV, JSON, Code (.py, .yaml, …) · je bis 5 MB · max. 40',
      'up.build': 'Brain erstellen', 'up.label_ing': 'Ingestion',
      'graph.title': 'Wissensgraph',
      'gate.sub': 'Die Antworten Ihres Unternehmens, fundiert in Ihren Dokumenten.',

      'set.language': 'Sprache', 'set.theme': 'App-Design', 'set.usage': 'Nutzungsstatistiken',
      'set.upgrade': 'Upgrade', 'set.account': 'Konto verwalten', 'set.signout': 'Trennen',
      'set.sign_in': 'Anmelden', 'set.system': 'Systemstandard', 'set.dark': 'Dunkles Design',
      'set.light': 'Helles Design',

      'view.title': 'Ansicht', 'view.sort_by': 'Sortieren nach', 'view.by_brain': 'Nach Brain',
      'view.timeline': 'Zeitstrahl', 'view.updated': 'Aktualisiert', 'view.created': 'Erstellt',
      'view.grouped': 'Nach Brain gruppiert', 'view.sorted': 'sortiert nach',
      'view.toggle': 'Anzeigen und sortieren',

      'usage.title': 'Nutzungsstatistiken', 'usage.sub': 'Letzte 30 Tage · geschätzte Tokens',
      'usage.feature': 'Funktion', 'usage.brain': 'Brain', 'usage.model': 'Modell',
      'usage.calls': 'Aufrufe', 'usage.tokens': 'Tokens', 'usage.time': 'Zeit',
      'usage.empty': 'Noch keine Modellaufrufe aufgezeichnet.', 'usage.signin': 'Melden Sie sich an, um die Nutzung zu sehen.',

      'up.title': 'Kestrel upgraden',
      'up.sub': 'Einfache Pläne, die mit Ihrem Company Brain wachsen.',
      'up.current': 'Aktueller Plan', 'up.soon': 'Demnächst', 'up.per_mo': '/Monat',
      'up.free': 'Kostenlos', 'up.pro': 'Pro', 'up.biz': 'Business',
      'up.free_f1': '1 Brain, bis zu 3 Mitglieder', 'up.free_f2': '200 Antworten pro Monat',
      'up.free_f3': 'Alle Exportformate',
      'up.pro_f1': 'Unbegrenzte Brains und Mitglieder', 'up.pro_f2': 'Unbegrenzte Antworten',
      'up.pro_f3': 'Prioritäre Modelle, längerer Kontext',
      'up.biz_f1': 'Org-Workspaces mit Rollen', 'up.biz_f2': 'SSO und Audit-Trail',
      'up.biz_f3': 'Prioritärer Support',
      'up.note': 'Der Checkout wird aktiviert, sobald die Pläne veröffentlicht sind. Alles, was Sie heute nutzen, bleibt kostenlos.',

      'stage.smalltalk': 'Direkter Chat — keine Suche nötig',
      'stage.plan': 'Suchagenten planen',
      'stage.router_chat': 'Allgemeiner Chat — Suche übersprungen',
      'stage.delegating': 'An Suchagenten delegiert',
    },

    zh: {
      'nav.workspace': '工作区', 'nav.ask': '提问', 'nav.new_brain': '新建大脑',
      'nav.brains': '大脑', 'nav.graph': '图谱', 'nav.chats': '对话',
      'nav.new_chat': '新对话', 'nav.no_chats': '暂无已保存的对话',
      'sb.connecting': '连接中…', 'sb.key_rejected': '· 密钥被拒',
      'sb.unreachable': '无法连接', 'brain.demo': '演示大脑',

      'greet.morning': '早上好，我能帮您什么？',
      'greet.afternoon': '下午好，我能帮您什么？',
      'greet.evening': '晚上好，我能帮您什么？',

      'composer.placeholder': '向公司的所有文档提问…',
      'composer.placeholder_brain': '向你上传的文档提问…',
      'menu.questions': '{n} 个问题',
      'composer.switch_brain': '切换大脑', 'composer.actions': '对话操作',
      'composer.attach': '为此消息附加文件', 'composer.send': '发送',
      'composer.stop': '停止生成',

      'menu.turns': '{n} 轮对话', 'menu.copy_transcript': '复制完整对话',
      'menu.add_docs': '向此大脑添加文档…', 'menu.export_md': '导出 Markdown',
      'menu.export_txt': '导出纯文本', 'menu.export_docx': '导出 Word 文档',
      'menu.export_pdf': '导出 PDF', 'menu.clear_chat': '清空对话',

      'files.title': '添加文档', 'files.drop': '拖拽文件到此处或选择文件',
      'files.hint': 'PDF、DOCX、TXT、MD、CSV、JSON、代码文件 · 每个最大 5 MB · 最多 40 个。直接加入此大脑 — 无需重启，立即可问答。',
      'files.add': '加入大脑', 'files.close': '关闭', 'files.choose': '选择文件',
      'src.copy': '复制', 'src.close': '关闭',
      'src.open': '打开此来源文档',

      'chip.demo1': '为什么 Bluepeak 续约存在风险？',
      'chip.demo2': '我们欠多少服务积分，谁批准的？',
      'chip.demo3': '续约和根因分析的负责人是谁？',
      'chip.demo4': '续约日期在各文档中一致吗？',
      'chip.gen1': '总结这个大脑里的内容',
      'chip.gen2': '下一步行动是什么？',
      'chip.gen3': '根据最新回答起草邮件',
      'chip.gen4': '所有内容相互一致吗？',

      'gate.title': '登录 Kestrel',
      'up.h1': '构建公司大脑',
      'up.sub': '上传你自己的文档。每个文件都会被读取、分块并转化为知识图谱 — 然后在与演示大脑相同的仪表板中提问。',
      'up.label_name': '大脑名称', 'up.name_ph': '例如 acme_contracts',
      'up.name_hint': '字母、数字和下划线，3–40 个字符。空格会变成下划线。',
      'up.label_docs': '文档', 'up.drop': '拖拽文件到此处', 'up.choose': '选择文件',
      'up.hint': 'PDF、DOCX、TXT、MD、CSV、JSON、代码文件（.py、.yaml 等）· 每个最大 5 MB · 最多 40 个',
      'up.build': '构建大脑', 'up.label_ing': '摄取',
      'graph.title': '知识图谱',
      'gate.sub': '您公司的答案，植根于您的文档。',

      'set.language': '语言', 'set.theme': '应用主题', 'set.usage': '用量统计',
      'set.upgrade': '升级', 'set.account': '管理账户', 'set.signout': '断开连接',
      'set.sign_in': '登录', 'set.system': '跟随系统', 'set.dark': '深色主题',
      'set.light': '浅色主题',

      'view.title': '视图', 'view.sort_by': '排序方式', 'view.by_brain': '按大脑',
      'view.timeline': '时间线', 'view.updated': '更新时间', 'view.created': '创建时间',
      'view.grouped': '按大脑分组', 'view.sorted': '排序：',
      'view.toggle': '视图与排序',

      'usage.title': '用量统计', 'usage.sub': '最近 30 天 · 估算 token',
      'usage.feature': '功能', 'usage.brain': '大脑', 'usage.model': '模型',
      'usage.calls': '调用', 'usage.tokens': 'Token', 'usage.time': '耗时',
      'usage.empty': '还没有模型调用记录。', 'usage.signin': '登录后查看用量。',

      'up.title': '升级 Kestrel',
      'up.sub': '随您的公司大脑一起成长的简单套餐。',
      'up.current': '当前套餐', 'up.soon': '即将推出', 'up.per_mo': '/月',
      'up.free': '免费版', 'up.pro': '专业版', 'up.biz': '企业版',
      'up.free_f1': '1 个大脑，最多 3 名成员', 'up.free_f2': '每月 200 次回答',
      'up.free_f3': '全部导出格式',
      'up.pro_f1': '无限大脑和成员', 'up.pro_f2': '无限回答',
      'up.pro_f3': '优先模型，更长上下文',
      'up.biz_f1': '带角色的组织工作区', 'up.biz_f2': 'SSO 与审计日志',
      'up.biz_f3': '优先支持',
      'up.note': '套餐在计费系统发布后即可开通付款。您今天使用的所有内容仍然免费。',

      'stage.smalltalk': '直接对话 — 无需检索',
      'stage.plan': '正在规划检索代理',
      'stage.router_chat': '普通对话 — 跳过检索',
      'stage.delegating': '正在委派检索代理',
    },
  };

  const LANGS = [
    { code: 'en', label: 'English' },
    { code: 'hi', label: 'हिन्दी' },
    { code: 'es', label: 'Español' },
    { code: 'fr', label: 'Français' },
    { code: 'de', label: 'Deutsch' },
    { code: 'zh', label: '中文' },
  ];

  // ------------------------------------------------------------------ i18n
  let lang = localStorage.getItem('kestrel.lang') || 'en';
  if (!DICT[lang]) lang = 'en';

  function t(key, fallback) {
    const d = DICT[lang] || {};
    return d[key] || DICT.en[key] || fallback || key;
  }

  function fmt(key, vars) {
    let s = t(key);
    for (const k in (vars || {})) s = s.split('{' + k + '}').join(vars[k]);
    return s;
  }

  function apply(root) {
    const r = root || document;
    r.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = t(el.getAttribute('data-i18n'), el.textContent);
    });
    r.querySelectorAll('[data-i18n-ph]').forEach(el => {
      el.placeholder = t(el.getAttribute('data-i18n-ph'), el.placeholder);
    });
    r.querySelectorAll('[data-i18n-title]').forEach(el => {
      el.title = t(el.getAttribute('data-i18n-title'), el.title);
    });
    document.documentElement.lang = lang;
  }

  function setLang(code) {
    if (!DICT[code]) return;
    lang = code;
    localStorage.setItem('kestrel.lang', code);
    apply();
    window.dispatchEvent(new CustomEvent('kestrel:lang', { detail: { lang: code } }));
  }

  // ----------------------------------------------------------------- theme
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const KTheme = {
    get theme() { return localStorage.getItem('kestrel.theme') || 'system'; },
    resolved() {
      const t = this.theme;
      if (t === 'dark' || t === 'light') return t;
      return media.matches ? 'dark' : 'light';
    },
    apply() { document.documentElement.dataset.theme = this.resolved(); },
    set(mode) {
      localStorage.setItem('kestrel.theme', mode);
      this.apply();
      window.dispatchEvent(new CustomEvent('kestrel:theme', { detail: { theme: mode } }));
    },
  };
  media.addEventListener('change', () => {
    if (KTheme.theme === 'system') {
      KTheme.apply();
      window.dispatchEvent(new CustomEvent('kestrel:theme', { detail: { theme: 'system' } }));
    }
  });
  KTheme.apply();

  window.KI18N = { t, fmt, apply, setLang, get lang() { return lang; }, LANGS };
  window.KTheme = KTheme;
  apply();
})();
