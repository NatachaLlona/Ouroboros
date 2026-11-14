/* Swagger authorization uses memory-only bearer tokens and same-origin HTTPS. */
function OuroborosAuthPlugin(system) {
  const React = system.React;
  const element = React.createElement;

  class AuthorizationPopup extends React.Component {
    constructor(props) {
      super(props);
      this.state = {
        login: "", appPassword: "", humanToken: "", clientId: "", clientSecret: "",
        humanMessage: "", clientMessage: "", busy: false
      };
      this.pending = false;
      this.alive = true;
      this.previousFocus = document.activeElement;
      this.controller = new AbortController();
      this.close = this.close.bind(this);
      this.escape = event => {
        if (event.key === "Escape") this.close();
        if (event.key === "Tab" && this.dialog) {
          const controls = [...this.dialog.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }
      };
    }

    componentDidMount() {
      document.addEventListener("keydown", this.escape);
      this.firstInput?.focus();
    }

    componentWillUnmount() {
      this.alive = false;
      this.controller.abort();
      document.removeEventListener("keydown", this.escape);
      this.previousFocus?.focus();
    }

    close() {
      system.authActions.showDefinitions(false);
    }

    clearAuthorization(names) {
      const current = system.authSelectors.authorized();
      const selected = names.filter(name => current?.has(name));
      if (selected.length) system.authActions.logout(selected);
    }

    field(id, label, stateKey, type, autocomplete) {
      return element("div", {className: "ouroboros-auth-field", key: id},
        element("label", {htmlFor: id}, label),
        element("input", {
          id, type, autoComplete: autocomplete, value: this.state[stateKey],
          disabled: this.state.busy, spellCheck: false,
          ref: id === "app-login" ? input => { this.firstInput = input; } : undefined,
          onChange: event => this.setState({[stateKey]: event.target.value})
        })
      );
    }

    async request(path, options) {
      const response = await fetch(path, {
        ...options, credentials: "omit", cache: "no-store", redirect: "error",
        signal: this.controller.signal
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error?.message || `Authentication failed (HTTP ${response.status}).`);
      }
      return payload;
    }

    async authorize(mode, event) {
      event.preventDefault();
      if (this.pending) return;
      this.pending = true;
      const {login, appPassword, humanToken, clientId, clientSecret} = this.state;
      const messageKey = mode === "client" ? "clientMessage" : "humanMessage";
      this.setState({busy: true, appPassword: "", clientSecret: "", humanToken: "", [messageKey]: ""});
      this.clearAuthorization(["HumanBearer", "OAuth2"]);
      try {
        if (location.protocol !== "https:") throw new Error("HTTPS is required for authorization.");
        let token;
        if (mode === "client") {
          token = await this.request("/oauth/token", {
            method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: new URLSearchParams({grant_type: "client_credentials", client_id: clientId, client_secret: clientSecret})
          });
          if (!token.access_token) throw new Error("The integration token response is invalid.");
          if (!this.alive) return;
          system.authActions.authorizeOauth2({
            auth: {name: "OAuth2", schema: {type: "oauth2", flow: "clientCredentials", tokenUrl: "/oauth/token", scopes: {}}, scopes: []},
            token
          });
        } else {
          token = mode === "paste" ? {access_token: humanToken.trim()} : await this.request("/auth/user-token", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({username: login, password: appPassword})
          });
          if (!token.access_token) throw new Error("Enter a human access token or sign in with an App Password.");
          const identity = await this.request("/me", {headers: {Authorization: "Bearer " + token.access_token}});
          if (identity.kind !== "human_password") throw new Error("Human Access Token requires a human token.");
          if (!this.alive) return;
          system.authActions.authorize({HumanBearer: {
            name: "HumanBearer", schema: {type: "http", scheme: "bearer"}, value: token.access_token
          }});
        }
        if (this.alive) this.setState({[messageKey]: "Authorized. Try it out will reuse this access token until it expires."});
      } catch (error) {
        if (this.alive && error.name !== "AbortError") {
          const message = error instanceof TypeError ? "Authentication service unavailable. Check the HTTPS connection." : error.message;
          this.setState({[messageKey]: message});
        }
      } finally {
        this.pending = false;
        if (this.alive) this.setState({busy: false});
      }
    }

    render() {
      const button = label => element("button", {type: "submit", className: "btn authorize", disabled: this.state.busy}, label);
      const authorized = system.authSelectors.authorized();
      return element("div", {className: "dialog-ux ouroboros-auth"},
        element("div", {className: "backdrop-ux", onClick: this.close}),
        element("div", {className: "modal-ux", role: "dialog", "aria-modal": "true", "aria-labelledby": "auth-title", ref: dialog => { this.dialog = dialog; }},
          element("div", {className: "modal-dialog-ux"}, element("div", {className: "modal-ux-inner"},
            element("div", {className: "modal-ux-header"},
              element("h3", {id: "auth-title"}, "Authorize"),
              element("button", {type: "button", className: "btn", onClick: this.close}, "Close")
            ),
            element("div", {className: "modal-ux-content"},
              element("section", {"aria-labelledby": "human-title"},
                element("h4", {id: "human-title"}, "App User"),
                element("p", null, "Sign in with your App User username and App Password. Your linked API User username is also accepted with the same App Password."),
                element("form", {onSubmit: event => this.authorize("human", event)},
                  this.field("app-login", "App User or linked API User", "login", "text", "username"),
                  this.field("app-password", "App Password", "appPassword", "password", "current-password"),
                  button("Sign in and authorize")
                ),
                element("form", {onSubmit: event => this.authorize("paste", event)},
                  this.field("human-token", "Human Access Token", "humanToken", "password", "off"),
                  button("Use human access token")
                ),
                element("p", {role: "status", "aria-live": "polite"}, this.state.humanMessage || (authorized?.has("HumanBearer") ? "Human access is authorized." : "")),
                element("button", {type: "button", className: "btn", disabled: this.state.busy, onClick: () => { this.clearAuthorization(["HumanBearer"]); this.setState({humanMessage: "Human access cleared."}); }}, "Clear human authorization")
              ),
              element("section", {"aria-labelledby": "client-title"},
                element("h4", {id: "client-title"}, "OAuth2 Client Credentials"),
                element("p", {id: "client-help"}, "Client ID is the client_id returned when integration credentials are issued. It is not an App User or API User username. Use the matching Client Secret. Create a separate integration API User through POST /api-users, or issue credentials for an eligible API User through POST /api-users/{id}/credentials. The reserved installation identity cannot receive Client Credentials. App Password and PostgreSQL Master Password are separate credentials."),
                element("form", {"aria-describedby": "client-help", onSubmit: event => this.authorize("client", event)},
                  this.field("client-id", "Client ID", "clientId", "text", "off"),
                  this.field("client-secret", "Client Secret", "clientSecret", "password", "off"),
                  button("Authorize integration")
                ),
                element("p", {role: "status", "aria-live": "polite"}, this.state.clientMessage || (authorized?.has("OAuth2") ? "Integration access is authorized." : "")),
                element("button", {type: "button", className: "btn", disabled: this.state.busy, onClick: () => { this.clearAuthorization(["OAuth2"]); this.setState({clientMessage: "Integration access cleared."}); }}, "Clear integration authorization")
              )
            )
          ))
        )
      );
    }
  }

  return {components: {authorizationPopup: AuthorizationPopup}};
}
