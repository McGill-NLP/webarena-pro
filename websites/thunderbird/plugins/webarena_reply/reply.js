/**
 * Render a cross-folder email conversation as a root-and-replies tree while
 * retaining links to the real IMAP messages and Roundcube compose actions.
 */
if (window.rcmail) {
  rcmail.addEventListener('plugin.webarena-thread-data', renderEmailConversation);

  rcmail.addEventListener('init', function() {
    if (!rcmail.env.uid || ['show', 'preview'].indexOf(rcmail.env.action) < 0) {
      return;
    }

    addNarrowReplyActions();
    rcmail.http_post('plugin.webarena-thread', {
      _uid: rcmail.env.uid,
      _mbox: rcmail.env.mailbox
    });
  });
}

function addNarrowReplyActions() {
  // Elastic finishes its responsive toolbar rearrangement during init.
  // Run immediately afterward so these controls remain in message content.
  window.setTimeout(function() {
    var messageHeader = document.querySelector('#message-header');

    if (!messageHeader || messageHeader.querySelector('.webarena-reply-actions')) {
      return;
    }

    var actions = document.createElement('div');
    actions.className = 'webarena-reply-actions';
    actions.setAttribute('role', 'toolbar');
    actions.setAttribute('aria-label', 'Reply actions');

    addNativeAction(actions, 'reply', 'Reply', 'webarena-reply');
    addNativeAction(actions, 'reply-all', 'Reply all', 'webarena-reply-all');

    var senderHeader = messageHeader.querySelector(':scope > .header');
    if (senderHeader) {
      senderHeader.insertAdjacentElement('afterend', actions);
    }
    else {
      messageHeader.appendChild(actions);
    }
  }, 0);
}

function addNativeAction(container, command, label, className) {
  var link = document.createElement('a');
  link.href = '#';
  link.className = className;
  link.setAttribute('role', 'button');
  link.textContent = label;
  link.addEventListener('click', function(event) {
    event.preventDefault();
    rcmail.command(command, '', link, event);
  });
  container.appendChild(link);
}

function renderEmailConversation(thread) {
  if (!thread || !thread.messages || thread.messages.length < 2) {
    return;
  }

  var frame = document.querySelector('.frame-content');
  if (!frame) {
    return;
  }

  var oldConversation = frame.querySelector('.webarena-conversation');
  if (oldConversation) {
    oldConversation.remove();
  }

  var byId = {};
  thread.messages.forEach(function(message) {
    byId[message.message_id] = message;
  });

  var conversation = element('section', 'webarena-conversation');
  conversation.setAttribute('data-testid', 'email-conversation');

  var heading = element('header', 'webarena-conversation-heading');
  var headingText = element('div', 'webarena-conversation-heading-text');
  var title = element('h2', '', thread.subject || 'Email conversation');
  var count = element(
    'div',
    'webarena-conversation-count',
    thread.messages.length + (thread.messages.length === 1 ? ' message' : ' messages')
  );
  headingText.appendChild(title);
  headingText.appendChild(count);
  heading.appendChild(headingText);
  conversation.appendChild(heading);

  var list = element('div', 'webarena-thread-list');
  list.setAttribute('data-testid', 'email-thread-list');
  thread.messages.forEach(function(message, index) {
    list.appendChild(renderThreadMessage(message, byId, index));
  });
  conversation.appendChild(list);

  frame.insertBefore(conversation, frame.firstChild);
  frame.classList.add('webarena-conversation-active');
}

function renderThreadMessage(message, byId, index) {
  var article = element(
    'article',
    'webarena-thread-message ' + (index === 0 ? 'root' : 'reply')
      + (message.current ? ' current' : '')
  );
  var depth = Math.min(Number(message.depth) || 0, 6);
  article.style.setProperty('--thread-depth', depth);
  article.setAttribute('data-message-id', message.message_id || '');
  article.setAttribute('data-folder', message.folder || '');
  article.setAttribute('data-depth', depth);
  article.setAttribute('data-testid', index === 0 ? 'thread-root-email' : 'thread-reply-email');

  var parent = byId[message.parent_message_id];
  if (index > 0) {
    var context = element('div', 'webarena-reply-context');
    context.appendChild(element('span', 'webarena-reply-arrow', '↳'));
    context.appendChild(document.createTextNode(
      ' Replying to ' + (parent && parent.from ? parent.from.name : 'the previous email')
    ));
    article.appendChild(context);
  }

  var row = element('div', 'webarena-thread-row');
  var sender = message.from || {name: 'Unknown sender', email: ''};
  row.appendChild(element('div', 'webarena-thread-avatar', initials(sender.name || sender.email)));

  var content = element('div', 'webarena-thread-content');
  var meta = element('div', 'webarena-thread-meta');
  var author = element('div', 'webarena-thread-author');
  author.appendChild(element('strong', '', sender.name || sender.email || 'Unknown sender'));
  if (sender.email) {
    author.appendChild(element('span', 'webarena-thread-email', '<' + sender.email + '>'));
  }
  meta.appendChild(author);

  var metaRight = element('div', 'webarena-thread-meta-right');
  metaRight.appendChild(element(
    'span',
    'webarena-folder-badge ' + (message.folder === 'Sent' ? 'sent' : 'inbox'),
    message.folder === 'Sent' ? 'Sent' : 'Inbox'
  ));
  metaRight.appendChild(element('time', '', formatThreadDate(message.date)));
  meta.appendChild(metaRight);
  content.appendChild(meta);

  var recipients = element('div', 'webarena-thread-recipients');
  var toNames = (message.to || []).map(personLabel).filter(Boolean);
  var ccNames = (message.cc || []).map(personLabel).filter(Boolean);
  recipients.textContent = 'To: ' + (toNames.join(', ') || 'undisclosed recipients');
  if (ccNames.length) {
    recipients.textContent += ' · Cc: ' + ccNames.join(', ');
  }
  content.appendChild(recipients);

  if (index > 0 && message.subject) {
    content.appendChild(element('div', 'webarena-thread-subject', message.subject));
  }

  content.appendChild(element('div', 'webarena-thread-body', message.body || ''));
  content.appendChild(renderMessageActions(message));
  row.appendChild(content);
  article.appendChild(row);
  return article;
}

function renderMessageActions(message) {
  var actions = element('div', 'webarena-thread-actions');
  if (!message.uid) {
    actions.appendChild(element('span', 'webarena-missing-message', 'Message unavailable'));
    return actions;
  }

  actions.appendChild(actionLink('Open email', {
    _task: 'mail',
    _action: 'show',
    _mbox: message.folder,
    _uid: message.uid
  }, 'open-email'));
  actions.appendChild(actionLink('Reply', {
    _task: 'mail',
    _action: 'compose',
    _mbox: message.folder,
    _reply_uid: message.uid
  }, 'reply-email'));
  actions.appendChild(actionLink('Reply all', {
    _task: 'mail',
    _action: 'compose',
    _mbox: message.folder,
    _reply_uid: message.uid,
    _all: 'all'
  }, 'reply-all-email'));
  return actions;
}

function actionLink(label, params, testId) {
  var link = element('a', '', label);
  link.href = '/?' + new URLSearchParams(params).toString();
  link.setAttribute('data-testid', testId);
  return link;
}

function element(tag, className, text) {
  var node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function initials(value) {
  var words = String(value || '?').trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map(function(word) { return word.charAt(0).toUpperCase(); }).join('') || '?';
}

function personLabel(person) {
  if (!person) {
    return '';
  }
  return person.name || person.email || '';
}

function formatThreadDate(value) {
  var date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || '';
  }
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}
